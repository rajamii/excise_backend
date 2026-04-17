import secrets
from decimal import Decimal

from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import serializers

from .models import (
    # PaymentBilldeskTransaction,
    # PaymentGatewayParameter,
    # PaymentHeadOfAccount,
    # PaymentHoaSplit,
    # PaymentModule,
    # PaymentModuleHoa,
    # PaymentWalletMaster,
    WalletBalance,
    WalletTransaction,
    _resolve_module_type_from_license_id,
    _resolve_wallet_row_licensee_id,
)
from .serializers import (
    # PaymentBilldeskTransactionSerializer,
    # PaymentGatewayParameterSerializer,
    # PaymentHeadOfAccountSerializer,
    # PaymentInitiateSerializer,
    # PaymentModuleHoaSerializer,
    # PaymentModuleSerializer,
    # PaymentStatusUpdateSerializer,
    # PaymentWalletMasterSerializer,
    WalletBalanceSerializer,
    WalletRechargeCreditSerializer,
    WalletTransactionSerializer,
)

def _wallet_license_candidates(raw_licensee_id: str):
    value = str(raw_licensee_id or "").strip()
    if not value:
        return []

    out = [value]

    # Basic alias expansion.
    if value.startswith("NLI/"):
        out.append(f"NA/{value[4:]}")
    elif value.startswith("NA/"):
        out.append(f"NLI/{value[3:]}")

    # Resolve through active licenses for source_object_id -> approved license_id mapping.
    try:
        from models.masters.license.models import License
        active_qs = License.objects.filter(is_active=True)
        by_license = active_qs.filter(license_id=value).order_by("-issue_date", "-license_id").first()
        if by_license and by_license.license_id:
            out.append(str(by_license.license_id).strip())
        by_source = active_qs.filter(source_object_id=value).order_by("-issue_date", "-license_id").first()
        if by_source and by_source.license_id:
            out.append(str(by_source.license_id).strip())
    except Exception:
        pass

    # Preserve order, remove duplicates/blanks.
    cleaned = []
    seen = set()
    for item in out:
        key = str(item or "").strip()
        if not key or key in seen:
            continue
        seen.add(key)
        cleaned.append(key)
    return cleaned


def _active_na_license_id_for_applicant(user) -> str:
    """Issued NA/... license id for this applicant (new license), if any."""
    if not user or not getattr(user, "is_authenticated", False):
        return ""
    try:
        from models.masters.license.models import License

        base = License.objects.filter(applicant=user, is_active=True)
        # Prefer any row whose license_id is already NA/... (do not rely on issue_date alone).
        lic = (
            base.filter(license_id__istartswith="NA/")
            .order_by("-issue_date", "-license_id")
            .first()
        )
        if lic and lic.license_id:
            return str(lic.license_id).strip()

        lic = (
            base.filter(source_type="new_license_application")
            .order_by("-issue_date", "-license_id")
            .first()
        )
        if lic and lic.license_id:
            lid = str(lic.license_id).strip()
            if lid.upper().startswith("NA/"):
                return lid
    except Exception:
        pass
    return ""


def _sync_wallet_balance_licensee_from_applicant_license(user, wallet) -> None:
    """
    Force wallet_balances.licensee_id (and module_type) from licenses when the ORM resolution
    missed (e.g. strict source_type). Uses QuerySet.update so it does not depend on save() paths.
    """
    if not user or not getattr(user, "is_authenticated", False) or not wallet:
        return
    try:
        from models.masters.license.models import License

        lic = (
            License.objects.filter(applicant=user, is_active=True)
            .filter(license_id__istartswith="NA/")
            .order_by("-issue_date", "-license_id")
            .first()
        )
        if not lic or not lic.license_id:
            return
        nid = str(lic.license_id).strip()
        if not nid:
            return
        mod = _resolve_module_type_from_license_id(nid, fallback=str(wallet.module_type or "other"))
        WalletBalance.objects.filter(wallet_balance_id=wallet.wallet_balance_id).update(
            licensee_id=nid,
            module_type=mod or str(wallet.module_type or "other"),
        )
        wallet.licensee_id = nid
        wallet.module_type = mod or wallet.module_type
    except Exception:
        pass


def _wallet_candidates_for_request(request, path_licensee_id: str):
    """
    License ids to match wallet rows: applicant's NA/... first, then path + profile expansion.
    """
    candidates = []
    na = _active_na_license_id_for_applicant(request.user)
    if na:
        candidates.append(na)
    candidates.extend(_wallet_license_candidates(path_licensee_id))
    try:
        profile = getattr(request.user, "supply_chain_profile", None)
        profile_licensee_id = str(getattr(profile, "licensee_id", "") or "").strip()
        if profile_licensee_id:
            candidates.extend(_wallet_license_candidates(profile_licensee_id))
    except Exception:
        pass
    if not candidates:
        candidates = [str(path_licensee_id or "").strip()]
    seen = set()
    out = []
    for c in candidates:
        c = str(c or "").strip()
        if c and c not in seen:
            seen.add(c)
            out.append(c)
    return out


def _generate_transaction_id() -> str:
    return timezone.now().strftime("TXN%Y%m%d%H%M%S%f")


def _generate_unique_utr() -> str:
    for _ in range(10):
        utr = f"UTR{timezone.now().strftime('%Y%m%d%H%M%S')}{secrets.token_hex(4).upper()}"
        if not PaymentBilldeskTransaction.objects.filter(pk=utr).exists():
            return utr
    raise RuntimeError("Unable to generate unique UTR")


def _safe_limit(raw_limit=None, default: int = 100, max_limit: int = 1000) -> int:
    try:
        if raw_limit is None:
            return default
        parsed = int(raw_limit)
        if parsed < 1:
            return default
        return min(parsed, max_limit)
    except (TypeError, ValueError):
        return default


# @api_view(["GET"])
# @permission_classes([IsAuthenticated])
# def payment_master_data(request):
#     module_code = request.query_params.get("module_code")

#     modules_qs = PaymentModule.objects.filter(visibility_status="Y").order_by("module_code")
#     gateways_qs = PaymentGatewayParameter.objects.filter(is_active="Y").order_by("sl_no")

#     if module_code:
#         module = get_object_or_404(modules_qs, module_code=module_code)
#         module_hoa_qs = (
#             PaymentModuleHoa.objects.filter(module_code_id=module.module_code, is_active="Y")
#             .select_related("head_of_account")
#             .order_by("head_of_account_id")
#         )
#         hoa_qs = PaymentHeadOfAccount.objects.filter(
#             head_of_account__in=module_hoa_qs.values_list("head_of_account_id", flat=True),
#             visible_status="Y",
#         ).order_by("head_of_account")
#     else:
#         module_hoa_qs = PaymentModuleHoa.objects.filter(is_active="Y").select_related("head_of_account")
#         hoa_qs = PaymentHeadOfAccount.objects.filter(visible_status="Y").order_by("head_of_account")

#     return Response(
#         {
#             "modules": PaymentModuleSerializer(modules_qs, many=True).data,
#             "module_hoa_mappings": PaymentModuleHoaSerializer(module_hoa_qs, many=True).data,
#             "hoas": PaymentHeadOfAccountSerializer(hoa_qs, many=True).data,
#             "gateways": PaymentGatewayParameterSerializer(gateways_qs, many=True).data,
#         }
#     )


# @api_view(["GET"])
# @permission_classes([IsAuthenticated])
# def payment_module_hoas(request, module_code):
#     module = get_object_or_404(PaymentModule, module_code=module_code)
#     mappings = (
#         PaymentModuleHoa.objects.filter(module_code_id=module.module_code, is_active="Y")
#         .select_related("head_of_account")
#         .order_by("head_of_account_id")
#     )
#     return Response(
#         {
#             "module_code": module.module_code,
#             "module_desc": module.module_desc,
#             "results": PaymentModuleHoaSerializer(mappings, many=True).data,
#         }
#     )


# @api_view(["GET"])
# @permission_classes([IsAuthenticated])
# def payment_wallet_balance(request, licensee_id):
#     qs = PaymentWalletMaster.objects.filter(licensee_id_no=licensee_id).order_by("head_of_account")
#     total = sum((row.wallet_amount for row in qs), Decimal("0.00"))
#     return Response(
#         {
#             "licensee_id": licensee_id,
#             "total_wallet_amount": total,
#             "count": qs.count(),
#             "results": PaymentWalletMasterSerializer(qs, many=True).data,
#         }
#     )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def wallet_summary(request, licensee_id):
    module_type = request.query_params.get("module_type")
    candidates = _wallet_candidates_for_request(request, licensee_id)
    request_user = str(getattr(request.user, "username", "") or "").strip()
    effective_id = _active_na_license_id_for_applicant(request.user) or str(licensee_id or "").strip()

    wallet_filter = Q(licensee_id__in=candidates)
    if request_user:
        wallet_filter |= Q(user_id__iexact=request_user)
    qs = WalletBalance.objects.filter(wallet_filter).order_by("wallet_type", "head_of_account")
    if module_type:
        qs = qs.filter(module_type__iexact=module_type)

    total = sum((row.current_balance for row in qs), Decimal("0.00"))
    return Response(
        {
            "licensee_id": effective_id,
            "total_wallet_amount": total,
            "count": qs.count(),
            "results": WalletBalanceSerializer(qs, many=True).data,
        }
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def wallet_recharge_list(request, licensee_id):
    candidates = _wallet_candidates_for_request(request, licensee_id)
    request_user = str(getattr(request.user, "username", "") or "").strip()
    effective_id = _active_na_license_id_for_applicant(request.user) or str(licensee_id or "").strip()
    tx_filter = Q(licensee_id__in=candidates)
    if request_user:
        tx_filter |= Q(user_id__iexact=request_user)

    qs = (
        WalletTransaction.objects.filter(
            tx_filter,
            transaction_type__iexact="recharge",
        )
        .order_by("-created_at")
    )

    wallet_type = request.query_params.get("wallet_type")
    if wallet_type:
        qs = qs.filter(wallet_type__iexact=wallet_type)

    head_of_account = request.query_params.get("head_of_account")
    if head_of_account:
        qs = qs.filter(head_of_account=head_of_account)

    limit = _safe_limit(request.query_params.get("limit"), default=200)
    qs = qs[:limit]

    return Response(
        {
            "licensee_id": effective_id,
            "count": len(qs),
            "results": WalletTransactionSerializer(qs, many=True).data,
        }
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def wallet_history_list(request, licensee_id):
    candidates = _wallet_candidates_for_request(request, licensee_id)
    request_user = str(getattr(request.user, "username", "") or "").strip()
    effective_id = _active_na_license_id_for_applicant(request.user) or str(licensee_id or "").strip()
    tx_filter = Q(licensee_id__in=candidates)
    if request_user:
        tx_filter |= Q(user_id__iexact=request_user)
    qs = WalletTransaction.objects.filter(tx_filter).order_by("-created_at")

    wallet_type = request.query_params.get("wallet_type")
    if wallet_type:
        qs = qs.filter(wallet_type__iexact=wallet_type)

    head_of_account = request.query_params.get("head_of_account")
    if head_of_account:
        qs = qs.filter(head_of_account=head_of_account)

    entry_type = request.query_params.get("entry_type")
    if entry_type:
        qs = qs.filter(entry_type__iexact=entry_type)

    limit = _safe_limit(request.query_params.get("limit"), default=500)
    qs = qs[:limit]

    return Response(
        {
            "licensee_id": effective_id,
            "count": len(qs),
            "results": WalletTransactionSerializer(qs, many=True).data,
        }
    )


def _normalize_wallet_type(wallet_type: str) -> str:
    value = str(wallet_type or "").strip().lower()
    if value in {"education", "educationcess", "education_cess", "education-cess"}:
        return "education_cess"
    return value


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def wallet_recharge_credit(request, licensee_id):
    """
    Dummy wallet recharge endpoint (testing only).

    Credits the selected wallet balance and inserts a row in wallet_transactions.
    The `transaction_id` provided by the frontend (Payment Details) is persisted as-is.
    """

    serializer = WalletRechargeCreditSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    data = serializer.validated_data
    request_user = str(getattr(request.user, "username", "") or "").strip()
    transaction_id = str(data["transaction_id"]).strip()
    wallet_type = _normalize_wallet_type(data["wallet_type"])
    head_of_account = str(data["head_of_account"]).strip()
    amount = Decimal(str(data["amount"])).quantize(Decimal("0.01"))
    remarks = str(data.get("remarks") or "").strip() or "Dummy wallet recharge credited (testing)."

    if not transaction_id:
        return Response({"detail": "transaction_id is required."}, status=status.HTTP_400_BAD_REQUEST)

    if not wallet_type:
        return Response({"detail": "wallet_type is required."}, status=status.HTTP_400_BAD_REQUEST)

    if not head_of_account:
        return Response({"detail": "head_of_account is required."}, status=status.HTTP_400_BAD_REQUEST)

    # Idempotency: avoid double credit when user clicks twice / retries.
    existing = WalletTransaction.objects.filter(
        transaction_id=transaction_id,
        transaction_type__iexact="recharge",
        entry_type__iexact="CR",
    ).order_by("-wallet_transaction_id").first()
    if existing:
        return Response(
            {
                "status": "ok",
                "already_processed": True,
                "wallet_transaction": WalletTransactionSerializer(existing).data,
            },
            status=status.HTTP_200_OK,
        )

    canonical_na = _active_na_license_id_for_applicant(request.user)
    candidates = _wallet_candidates_for_request(request, licensee_id)

    wallet_filter = Q(licensee_id__in=candidates)
    if request_user:
        wallet_filter |= Q(user_id__iexact=request_user)

    with transaction.atomic():
        wallet = (
            WalletBalance.objects.select_for_update()
            .filter(wallet_filter, wallet_type__iexact=wallet_type, head_of_account=head_of_account)
            .order_by("wallet_balance_id")
            .first()
        )
        if not wallet:
            # Auto-create wallet balance row for existing licenses where initializer didn't run yet.
            now_ts = timezone.now()
            template = (
                WalletBalance.objects.select_for_update()
                .filter(wallet_filter)
                .order_by("wallet_balance_id")
                .first()
            )

            template_licensee_id = str(getattr(template, "licensee_id", "") or "").strip() if template else ""
            raw_licensee = template_licensee_id or str(licensee_id or "").strip()
            resolved_licensee_id = (
                canonical_na
                or _resolve_wallet_row_licensee_id(raw_licensee, request_user or "")
                or raw_licensee
            )

            template_module_type = str(getattr(template, "module_type", "") or "").strip() if template else ""
            resolved_module_type = template_module_type or _resolve_module_type_from_license_id(
                resolved_licensee_id,
                fallback="other",
            )

            wallet = WalletBalance.objects.create(
                licensee_id=resolved_licensee_id,
                licensee_name=getattr(template, "licensee_name", "") if template else "",
                manufacturing_unit=getattr(template, "manufacturing_unit", "") if template else "",
                user_id=request_user or (getattr(template, "user_id", "") if template else ""),
                module_type=resolved_module_type or "distillery",
                wallet_type=wallet_type,
                head_of_account=head_of_account,
                opening_balance=Decimal("0.00"),
                total_credit=Decimal("0.00"),
                total_debit=Decimal("0.00"),
                current_balance=Decimal("0.00"),
                last_updated_at=now_ts,
                created_at=now_ts,
            )

        # Prefer issued NA/... from licenses table when the logged-in user is the applicant.
        if canonical_na:
            wallet.licensee_id = canonical_na

        # Direct sync from licenses (covers cases where helper queries or ORM resolution miss).
        _sync_wallet_balance_licensee_from_applicant_license(request.user, wallet)

        before = Decimal(str(wallet.current_balance or 0)).quantize(Decimal("0.01"))
        after = (before + amount).quantize(Decimal("0.01"))
        now_ts = timezone.now()

        wallet.current_balance = after
        wallet.total_credit = (Decimal(str(wallet.total_credit or 0)) + amount).quantize(Decimal("0.01"))
        wallet.last_updated_at = now_ts
        wallet.save(update_fields=["current_balance", "total_credit", "last_updated_at"])

        tx_licensee_id = (
            str(wallet.licensee_id or "").strip()
            or canonical_na
            or str(licensee_id or "").strip()
        )

        created = WalletTransaction.objects.create(
            wallet_balance=wallet,
            transaction_id=transaction_id,
            licensee_id=tx_licensee_id,
            licensee_name=wallet.licensee_name,
            user_id=request_user or str(wallet.user_id or ""),
            module_type=str(wallet.module_type or ""),
            wallet_type=str(wallet.wallet_type or wallet_type),
            head_of_account=str(wallet.head_of_account or head_of_account),
            entry_type="CR",
            transaction_type="recharge",
            amount=amount,
            balance_before=before,
            balance_after=after,
            reference_no=transaction_id,
            source_module="wallet_recharge_dummy",
            payment_status="success",
            remarks=remarks,
            created_at=now_ts,
        )

    return Response(
        {
            "status": "ok",
            "already_processed": False,
            "wallet_transaction": WalletTransactionSerializer(created).data,
            "wallet_balance": WalletBalanceSerializer(wallet).data,
        },
        status=status.HTTP_201_CREATED,
    )


# @api_view(["GET"])
# @permission_classes([IsAuthenticated])
# def payment_transaction_list(request):
#     qs = PaymentBilldeskTransaction.objects.all().order_by("-transaction_date")

#     if request.query_params.get("payer_id"):
#         qs = qs.filter(payer_id=request.query_params["payer_id"])
#     if request.query_params.get("payment_module_code"):
#         qs = qs.filter(payment_module_code=request.query_params["payment_module_code"])
#     if request.query_params.get("payment_status"):
#         qs = qs.filter(payment_status=request.query_params["payment_status"])
#     if request.query_params.get("utr"):
#         qs = qs.filter(utr=request.query_params["utr"])

#     limit = int(request.query_params.get("limit", "50"))
#     qs = qs[: max(1, min(limit, 500))]

#     return Response(
#         {
#             "count": len(qs),
#             "results": PaymentBilldeskTransactionSerializer(qs, many=True).data,
#         }
#     )


# @api_view(["GET"])
# @permission_classes([IsAuthenticated])
# def payment_transaction_detail(request, utr):
#     obj = get_object_or_404(PaymentBilldeskTransaction, pk=utr)
#     return Response(PaymentBilldeskTransactionSerializer(obj).data)


# @api_view(["POST"])
# @permission_classes([IsAuthenticated])
# def payment_initiate(request):
#     serializer = PaymentInitiateSerializer(data=request.data)
#     if not serializer.is_valid():
#         return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

#     data = serializer.validated_data
#     module = get_object_or_404(PaymentModule, module_code=data["payment_module_code"])
#     module_hoas = set(
#         PaymentModuleHoa.objects.filter(
#             module_code_id=module.module_code,
#             is_active="Y",
#         ).values_list("head_of_account_id", flat=True)
#     )
#     requested_hoas = {item["head_of_account"] for item in data["items"]}
#     invalid_hoas = sorted(requested_hoas - module_hoas)
#     if invalid_hoas:
#         return Response(
#             {
#                 "detail": "One or more HOAs are not configured for this module.",
#                 "invalid_hoas": invalid_hoas,
#             },
#             status=status.HTTP_400_BAD_REQUEST,
#         )

#     gateway_qs = PaymentGatewayParameter.objects.filter(is_active="Y")
#     gateway_sl_no = data.get("gateway_sl_no")
#     if gateway_sl_no is not None:
#         gateway = get_object_or_404(gateway_qs, sl_no=gateway_sl_no)
#     else:
#         gateway = gateway_qs.order_by("sl_no").first()
#         if gateway is None:
#             return Response(
#                 {"detail": "No active payment gateway configuration found."},
#                 status=status.HTTP_400_BAD_REQUEST,
#             )

#     transaction_id = _generate_transaction_id()
#     utr = _generate_unique_utr()
#     total_amount = sum((item["amount"] for item in data["items"]), Decimal("0.00"))
#     request_user_id = data.get("user_id") or getattr(request.user, "username", None)

#     with transaction.atomic():
#         txn = PaymentBilldeskTransaction.objects.create(
#             utr=utr,
#             transaction_id_no_hoa=transaction_id,
#             payer_id=data["payer_id"],
#             payment_module_code=module.module_code,
#             transaction_amount=total_amount,
#             request_merchantid=gateway.merchantid,
#             request_securityid=gateway.securityid,
#             request_return_url=gateway.return_url,
#             payment_status="P",
#             user_id=request_user_id,
#         )

#         PaymentHoaSplit.objects.bulk_create(
#             [
#                 PaymentHoaSplit(
#                     transaction_id_no=transaction_id,
#                     head_of_account=item["head_of_account"],
#                     payer_id=data["payer_id"],
#                     amount=item["amount"],
#                     payment_module_code=module.module_code,
#                     requisition_id_no=data.get("requisition_id_no") or None,
#                     user_id=request_user_id,
#                 )
#                 for item in data["items"]
#             ]
#         )

#     return Response(
#         {
#             "status": "ok",
#             "transaction_id": transaction_id,
#             "utr": utr,
#             "payment_status": txn.payment_status,
#             "transaction_amount": total_amount,
#             "gateway": {
#                 "sl_no": gateway.sl_no,
#                 "name": gateway.payment_gateway_name,
#                 "merchantid": gateway.merchantid,
#                 "return_url": gateway.return_url,
#             },
#         },
#         status=status.HTTP_201_CREATED,
#     )


# @api_view(["PATCH"])
# @permission_classes([IsAuthenticated])
# def payment_update_status(request, utr):
#     obj = get_object_or_404(PaymentBilldeskTransaction, pk=utr)
#     serializer = PaymentStatusUpdateSerializer(data=request.data)
#     if not serializer.is_valid():
#         return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

#     data = serializer.validated_data
#     obj.payment_status = data["payment_status"]
#     obj.response_authstatus = data.get("response_authstatus", obj.response_authstatus)
#     obj.response_errorstatus = data.get("response_errorstatus", obj.response_errorstatus)
#     obj.response_errordescription = data.get(
#         "response_errordescription", obj.response_errordescription
#     )
#     obj.response_string = data.get("response_string", obj.response_string)
#     obj.response_txnreferenceno = data.get("response_txnreferenceno", obj.response_txnreferenceno)
#     obj.response_bankreferenceno = data.get(
#         "response_bankreferenceno", obj.response_bankreferenceno
#     )
#     obj.response_txnamount = data.get("response_txnamount", obj.response_txnamount)
#     obj.response_txndate = data.get("response_txndate", obj.response_txndate)
#     obj.opr_date = timezone.now()
#     obj.save()

#     return Response(PaymentBilldeskTransactionSerializer(obj).data)
