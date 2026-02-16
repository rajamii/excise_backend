import secrets
from decimal import Decimal

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import (
    PaymentBilldeskTransaction,
    PaymentGatewayParameter,
    PaymentHeadOfAccount,
    PaymentHoaSplit,
    PaymentModule,
    PaymentModuleHoa,
    PaymentWalletMaster,
)
from .serializers import (
    PaymentBilldeskTransactionSerializer,
    PaymentGatewayParameterSerializer,
    PaymentHeadOfAccountSerializer,
    PaymentInitiateSerializer,
    PaymentModuleHoaSerializer,
    PaymentModuleSerializer,
    PaymentStatusUpdateSerializer,
    PaymentWalletMasterSerializer,
)


def _generate_transaction_id() -> str:
    return timezone.now().strftime("TXN%Y%m%d%H%M%S%f")


def _generate_unique_utr() -> str:
    for _ in range(10):
        utr = f"UTR{timezone.now().strftime('%Y%m%d%H%M%S')}{secrets.token_hex(4).upper()}"
        if not PaymentBilldeskTransaction.objects.filter(pk=utr).exists():
            return utr
    raise RuntimeError("Unable to generate unique UTR")


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def payment_master_data(request):
    module_code = request.query_params.get("module_code")

    modules_qs = PaymentModule.objects.filter(visibility_status="Y").order_by("module_code")
    gateways_qs = PaymentGatewayParameter.objects.filter(is_active="Y").order_by("sl_no")

    if module_code:
        module = get_object_or_404(modules_qs, module_code=module_code)
        module_hoa_qs = (
            PaymentModuleHoa.objects.filter(module_code_id=module.module_code, is_active="Y")
            .select_related("head_of_account")
            .order_by("head_of_account_id")
        )
        hoa_qs = PaymentHeadOfAccount.objects.filter(
            head_of_account__in=module_hoa_qs.values_list("head_of_account_id", flat=True),
            visible_status="Y",
        ).order_by("head_of_account")
    else:
        module_hoa_qs = PaymentModuleHoa.objects.filter(is_active="Y").select_related("head_of_account")
        hoa_qs = PaymentHeadOfAccount.objects.filter(visible_status="Y").order_by("head_of_account")

    return Response(
        {
            "modules": PaymentModuleSerializer(modules_qs, many=True).data,
            "module_hoa_mappings": PaymentModuleHoaSerializer(module_hoa_qs, many=True).data,
            "hoas": PaymentHeadOfAccountSerializer(hoa_qs, many=True).data,
            "gateways": PaymentGatewayParameterSerializer(gateways_qs, many=True).data,
        }
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def payment_module_hoas(request, module_code):
    module = get_object_or_404(PaymentModule, module_code=module_code)
    mappings = (
        PaymentModuleHoa.objects.filter(module_code_id=module.module_code, is_active="Y")
        .select_related("head_of_account")
        .order_by("head_of_account_id")
    )
    return Response(
        {
            "module_code": module.module_code,
            "module_desc": module.module_desc,
            "results": PaymentModuleHoaSerializer(mappings, many=True).data,
        }
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def payment_wallet_balance(request, licensee_id):
    qs = PaymentWalletMaster.objects.filter(licensee_id_no=licensee_id).order_by("head_of_account")
    total = sum((row.wallet_amount for row in qs), Decimal("0.00"))
    return Response(
        {
            "licensee_id": licensee_id,
            "total_wallet_amount": total,
            "count": qs.count(),
            "results": PaymentWalletMasterSerializer(qs, many=True).data,
        }
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def payment_transaction_list(request):
    qs = PaymentBilldeskTransaction.objects.all().order_by("-transaction_date")

    if request.query_params.get("payer_id"):
        qs = qs.filter(payer_id=request.query_params["payer_id"])
    if request.query_params.get("payment_module_code"):
        qs = qs.filter(payment_module_code=request.query_params["payment_module_code"])
    if request.query_params.get("payment_status"):
        qs = qs.filter(payment_status=request.query_params["payment_status"])
    if request.query_params.get("utr"):
        qs = qs.filter(utr=request.query_params["utr"])

    limit = int(request.query_params.get("limit", "50"))
    qs = qs[: max(1, min(limit, 500))]

    return Response(
        {
            "count": len(qs),
            "results": PaymentBilldeskTransactionSerializer(qs, many=True).data,
        }
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def payment_transaction_detail(request, utr):
    obj = get_object_or_404(PaymentBilldeskTransaction, pk=utr)
    return Response(PaymentBilldeskTransactionSerializer(obj).data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def payment_initiate(request):
    serializer = PaymentInitiateSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    data = serializer.validated_data
    module = get_object_or_404(PaymentModule, module_code=data["payment_module_code"])
    module_hoas = set(
        PaymentModuleHoa.objects.filter(
            module_code_id=module.module_code,
            is_active="Y",
        ).values_list("head_of_account_id", flat=True)
    )
    requested_hoas = {item["head_of_account"] for item in data["items"]}
    invalid_hoas = sorted(requested_hoas - module_hoas)
    if invalid_hoas:
        return Response(
            {
                "detail": "One or more HOAs are not configured for this module.",
                "invalid_hoas": invalid_hoas,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    gateway_qs = PaymentGatewayParameter.objects.filter(is_active="Y")
    gateway_sl_no = data.get("gateway_sl_no")
    if gateway_sl_no is not None:
        gateway = get_object_or_404(gateway_qs, sl_no=gateway_sl_no)
    else:
        gateway = gateway_qs.order_by("sl_no").first()
        if gateway is None:
            return Response(
                {"detail": "No active payment gateway configuration found."},
                status=status.HTTP_400_BAD_REQUEST,
            )

    transaction_id = _generate_transaction_id()
    utr = _generate_unique_utr()
    total_amount = sum((item["amount"] for item in data["items"]), Decimal("0.00"))
    request_user_id = data.get("user_id") or getattr(request.user, "username", None)

    with transaction.atomic():
        txn = PaymentBilldeskTransaction.objects.create(
            utr=utr,
            transaction_id_no_hoa=transaction_id,
            payer_id=data["payer_id"],
            payment_module_code=module.module_code,
            transaction_amount=total_amount,
            request_merchantid=gateway.merchantid,
            request_securityid=gateway.securityid,
            request_return_url=gateway.return_url,
            payment_status="P",
            user_id=request_user_id,
        )

        PaymentHoaSplit.objects.bulk_create(
            [
                PaymentHoaSplit(
                    transaction_id_no=transaction_id,
                    head_of_account=item["head_of_account"],
                    payer_id=data["payer_id"],
                    amount=item["amount"],
                    payment_module_code=module.module_code,
                    requisition_id_no=data.get("requisition_id_no") or None,
                    user_id=request_user_id,
                )
                for item in data["items"]
            ]
        )

    return Response(
        {
            "status": "ok",
            "transaction_id": transaction_id,
            "utr": utr,
            "payment_status": txn.payment_status,
            "transaction_amount": total_amount,
            "gateway": {
                "sl_no": gateway.sl_no,
                "name": gateway.payment_gateway_name,
                "merchantid": gateway.merchantid,
                "return_url": gateway.return_url,
            },
        },
        status=status.HTTP_201_CREATED,
    )


@api_view(["PATCH"])
@permission_classes([IsAuthenticated])
def payment_update_status(request, utr):
    obj = get_object_or_404(PaymentBilldeskTransaction, pk=utr)
    serializer = PaymentStatusUpdateSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    data = serializer.validated_data
    obj.payment_status = data["payment_status"]
    obj.response_authstatus = data.get("response_authstatus", obj.response_authstatus)
    obj.response_errorstatus = data.get("response_errorstatus", obj.response_errorstatus)
    obj.response_errordescription = data.get(
        "response_errordescription", obj.response_errordescription
    )
    obj.response_string = data.get("response_string", obj.response_string)
    obj.response_txnreferenceno = data.get("response_txnreferenceno", obj.response_txnreferenceno)
    obj.response_bankreferenceno = data.get(
        "response_bankreferenceno", obj.response_bankreferenceno
    )
    obj.response_txnamount = data.get("response_txnamount", obj.response_txnamount)
    obj.response_txndate = data.get("response_txndate", obj.response_txndate)
    obj.opr_date = timezone.now()
    obj.save()

    return Response(PaymentBilldeskTransactionSerializer(obj).data)
