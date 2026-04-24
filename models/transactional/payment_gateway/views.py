import hashlib
import hmac
import html
import logging
from urllib.parse import urlencode
from decimal import Decimal
import secrets

from django.conf import settings
from django.db.utils import OperationalError, ProgrammingError
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import redirect
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.urls import reverse
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import PaymentBilldeskTransaction, PaymentGatewayParameters, PaymentSendHOA, MasterPaymentModule


from models.transactional.wallet.wallet_service import credit_wallet_balance, record_wallet_transaction

logger = logging.getLogger(__name__)

LICENSE_FEE_HOA = "0039-00-800-45-02"
SECURITY_DEPOSIT_HOA_SENTINEL = "non"
DEFAULT_LICENSE_RENEWAL_MODULE_CODE = "002"
DEFAULT_WALLET_ADVANCE_MODULE_CODE = "999"


def _normalize_wallet_type(wallet_type: str) -> str:
    value = str(wallet_type or "").strip().lower().replace(" ", "_").replace("-", "_")
    if value in {"education", "educationcess", "education_cess", "educationcesswallet", "education_cess_wallet"}:
        return "education_cess"
    if value in {"excise", "excise_duty", "excise_duty_wallet", "exciseduty", "excise_wallet"}:
        return "excise"
    return value


def _active_na_license_id_for_applicant(user) -> str:
    if not user or not getattr(user, "is_authenticated", False):
        return ""
    try:
        from models.masters.license.models import License

        base = License.objects.filter(applicant=user, is_active=True)
        lic = base.filter(license_id__istartswith="NA/").order_by("-issue_date", "-license_id").first()
        if lic and lic.license_id:
            return str(lic.license_id).strip()

        lic = base.filter(source_type="new_license_application").order_by("-issue_date", "-license_id").first()
        if lic and lic.license_id:
            lid = str(lic.license_id).strip()
            if lid.upper().startswith("NA/"):
                return lid
    except Exception:
        pass
    return ""


def _billdesk_hmac_sha256(msg: str, key: str) -> str:
    return hmac.new(key.encode(), msg.encode(), hashlib.sha256).hexdigest().upper()


def _normalize_amount(raw_amount) -> Decimal:
    value = Decimal(str(raw_amount or "0")).quantize(Decimal("0.01"))
    if value <= 0:
        raise ValueError("amount must be greater than zero")
    return value


def _validate_payment_module_code(module_code: str) -> str:
    code = str(module_code or "").strip()
    if not code:
        raise ValueError("payment_module_code is required.")

    # Prefer legacy eabgari_master_module if it exists in the DB.
    try:
        if MasterPaymentModule.objects.filter(module_code=code).exists():
            return code
    except (OperationalError, ProgrammingError):
        pass

    # Fallback to SEMS master table (common in this codebase).
    try:
        if MasterPaymentModule.objects.filter(module_code=code).exists():
            return code
    except Exception:
        pass

    raise ValueError(f"Invalid payment_module_code={code}. Not found in master module table.")


def _generate_transaction_id(prefix: str = "TXN") -> str:
    return f"{prefix}{timezone.now().strftime('%Y%m%d%H%M%S')}{secrets.token_hex(4).upper()}"


def _build_billdesk_request_message(
    *,
    merchant_id: str,
    transaction_id: str,
    amount_str: str,
    security_id: str,
    return_url: str,
    additional_infos: list[str],
) -> str:
    infos = [(str(x or "").strip() or "NA") for x in (additional_infos or [])][:7]
    while len(infos) < 7:
        infos.append("NA")

    return (
        f"{merchant_id}|{transaction_id}|NA|{amount_str}|NA|NA|NA|INR|NA|R|{security_id}|NA|NA|F|"
        f"{infos[0]}|{infos[1]}|{infos[2]}|{infos[3]}|{infos[4]}|{infos[5]}|{infos[6]}|{return_url}"
    )


def _build_full_name_from_user(user) -> str:
    if not user:
        return ""
    parts = []
    for key in ("first_name", "middle_name", "last_name"):
        value = str(getattr(user, key, "") or "").strip()
        if value:
            parts.append(value)
    full = " ".join(parts).strip()
    if full:
        return full
    # Fallbacks commonly present on custom user/profile models.
    for key in ("name", "full_name", "fullname"):
        value = str(getattr(user, key, "") or "").strip()
        if value:
            return value
    return ""


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def billdesk_initiate_wallet_recharge(request):
    data = request.data or {}

    transaction_id = str(data.get("transaction_id") or "").strip()
    wallet_type = _normalize_wallet_type(data.get("wallet_type"))
    head_of_account = str(data.get("head_of_account") or "").strip()
    payment_module_code = str(data.get("payment_module_code") or "").strip()
    payer_id = str(data.get("payer_id") or getattr(request.user, "username", "") or "").strip()[:50]
    raw_amount = data.get("amount")

    if not transaction_id:
        return Response({"detail": "transaction_id is required."}, status=status.HTTP_400_BAD_REQUEST)
    if not wallet_type:
        return Response({"detail": "wallet_type is required."}, status=status.HTTP_400_BAD_REQUEST)
    if not head_of_account:
        return Response({"detail": "head_of_account is required."}, status=status.HTTP_400_BAD_REQUEST)

    # Keep this endpoint backward-compatible with existing UI: module code is optional here.
    # When provided, it should map to the master module table; otherwise store a stable default.
    if payment_module_code:
        try:
            payment_module_code = _validate_payment_module_code(payment_module_code)
        except Exception:
            # Do not block recharge initiation for legacy clients.
            logger.warning("Unknown payment_module_code=%s for wallet recharge; storing as-is.", payment_module_code)
    else:
        # eabgari_master_module: 999 = Advance Payment to e-Wallet
        payment_module_code = DEFAULT_WALLET_ADVANCE_MODULE_CODE
        try:
            payment_module_code = _validate_payment_module_code(payment_module_code)
        except Exception:
            # If the master table isn't available in this environment, still store something stable.
            payment_module_code = DEFAULT_WALLET_ADVANCE_MODULE_CODE

    try:
        amount = _normalize_amount(raw_amount)
    except Exception as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    gateway = (
        PaymentGatewayParameters.objects.filter(is_active="Y", payment_gateway_name__iexact="Billdesk")
        .order_by("sl_no")
        .first()
    )
    if gateway is None:
        return Response(
            {"detail": "No active Billdesk configuration found in Payment_Gateway_Parameters."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if getattr(settings, "BILLDESK_USE_MOCK", False):
        billdesk_url = request.build_absolute_uri(reverse("payment_gateway:billdesk-mock-process"))
    else:
        billdesk_url = getattr(settings, "BILLDESK_GATEWAY_URL", "") or ""
    if not billdesk_url:
        return Response(
            {"detail": "BILLDESK_GATEWAY_URL is not configured on server."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    if getattr(settings, "BILLDESK_USE_MOCK", False):
        return_url = request.build_absolute_uri(reverse("payment_gateway:billdesk-response"))
    else:
        return_url = str(gateway.return_url or "").strip()
    if not return_url:
        return Response(
            {"detail": "return_url is not configured for Billdesk in Payment_Gateway_Parameters."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    merchant_id = str(gateway.merchantid or "").strip()
    security_id = str(gateway.securityid or "").strip()
    encryption_key = str(gateway.encryption_key or "").strip()
    if not merchant_id or not security_id or not encryption_key:
        return Response(
            {"detail": "Billdesk gateway config is missing merchantid/securityid/encryption_key."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    amount_str = f"{amount:.2f}"
    additional_info1 = head_of_account
    additional_info2 = "WALLET"
    # Keep walletType directly so the Angular success screen can display it as-is.
    additional_info3 = wallet_type

    msg_without_checksum = _build_billdesk_request_message(
        merchant_id=merchant_id,
        transaction_id=transaction_id,
        amount_str=amount_str,
        security_id=security_id,
        return_url=return_url,
        additional_infos=[
            additional_info1,
            additional_info2,
            additional_info3,
            "NA",
            "NA",
            "NA",
            "NA",
        ],
    )
    checksum = _billdesk_hmac_sha256(msg_without_checksum, encryption_key)
    request_msg = f"{msg_without_checksum}|{checksum}"

    PaymentBilldeskTransaction.objects.update_or_create(
        utr=transaction_id,
        defaults={
            "transaction_date": timezone.now(),
            "transaction_id_no_hoa": transaction_id,
            "payer_id": payer_id,
            "payment_module_code": payment_module_code,
            "transaction_amount": amount,
            "request_merchantid": merchant_id,
            "request_currencytype": "INR",
            "request_typefield1": "R",
            "request_securityid": security_id,
            "request_typefield2": "F",
            "request_additionalinfo1": additional_info1,
            "request_additionalinfo2": additional_info2,
            "request_additionalinfo3": additional_info3,
            "request_additionalinfo4": "NA",
            "request_additionalinfo5": "NA",
            "request_additionalinfo6": "NA",
            "request_additionalinfo7": "NA",
            "request_return_url": return_url,
            "request_checksum": checksum,
            "request_string": request_msg,
            "payment_status": "P",
            "opr_date": timezone.now(),
            "user_id": str(getattr(request.user, "username", "") or "").strip()[:50],
        },
    )

    PaymentSendHOA.objects.update_or_create(
        transaction_id_no=transaction_id,
        head_of_account=head_of_account,
        defaults={
            "licensee_id": str(data.get("licensee_id") or data.get("licenseeId") or payer_id or "").strip()[:50] or None,
            "amount": amount,
            "payment_module_code": payment_module_code,
            "requisition_no": (_active_na_license_id_for_applicant(request.user) or "NA")[:50],
            "opr_date": timezone.now(),
        },
    )

    return Response(
        {
            "billdesk_url": billdesk_url,
            "request_msg": request_msg,
            "transaction_id": transaction_id,
        }
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def billdesk_initiate_license_fee(request):
    """
    License fee top-up via BillDesk.

    As per payment logic document:
    - AdditionalInfo1: Head of Account (0039-00-800-45-02)
    - AdditionalInfo2: SIKPAY
    - AdditionalInfo3: SIKPAY
    """
    data = request.data or {}

    transaction_id = str(data.get("transaction_id") or "").strip() or _generate_transaction_id("SIKPAY")
    payer_id = str(data.get("payer_id") or data.get("licensee_id") or "").strip()[:50]
    # sems_payment_transaction_billdesk.payment_module_code must store a module_code from eabgari_master_module.
    # Defaulting to Licensee Renewal (002) keeps legacy clients working.
    payment_module_code = str(data.get("payment_module_code") or "").strip() or DEFAULT_LICENSE_RENEWAL_MODULE_CODE
    raw_amount = data.get("amount")

    if not payer_id:
        return Response({"detail": "payer_id (licensee id) is required."}, status=status.HTTP_400_BAD_REQUEST)

    try:
        payment_module_code = _validate_payment_module_code(payment_module_code)
    except Exception as exc:
        # Do not hard-block initiation if the master module table is missing/out-of-sync in an env.
        # License renewal module code (002) is stable enough to proceed and still record the raw value.
        logger.warning(
            "Invalid payment_module_code=%s for license fee initiation; proceeding with raw value. err=%s",
            payment_module_code,
            exc,
        )

    try:
        amount = _normalize_amount(raw_amount)
    except Exception as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    gateway = (
        PaymentGatewayParameters.objects.filter(is_active="Y", payment_gateway_name__iexact="Billdesk")
        .order_by("sl_no")
        .first()
    )
    if gateway is None:
        return Response(
            {"detail": "No active Billdesk configuration found in Payment_Gateway_Parameters."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if getattr(settings, "BILLDESK_USE_MOCK", False):
        billdesk_url = request.build_absolute_uri(reverse("payment_gateway:billdesk-mock-process"))
        return_url = request.build_absolute_uri(reverse("payment_gateway:billdesk-response"))
    else:
        billdesk_url = getattr(settings, "BILLDESK_GATEWAY_URL", "") or ""
        return_url = str(gateway.return_url or "").strip()

    if not billdesk_url:
        return Response({"detail": "BILLDESK_GATEWAY_URL is not configured on server."}, status=500)
    if not return_url:
        return Response({"detail": "return_url is not configured for Billdesk in Payment_Gateway_Parameters."}, status=500)

    merchant_id = str(gateway.merchantid or "").strip()
    security_id = str(gateway.securityid or "").strip()
    encryption_key = str(gateway.encryption_key or "").strip()
    if not merchant_id or not security_id or not encryption_key:
        return Response({"detail": "Billdesk gateway config is missing merchantid/securityid/encryption_key."}, status=500)

    amount_str = f"{amount:.2f}"
    add1 = LICENSE_FEE_HOA
    add2 = "SIKPAY"
    add3 = "SIKPAY"

    msg_without_checksum = _build_billdesk_request_message(
        merchant_id=merchant_id,
        transaction_id=transaction_id,
        amount_str=amount_str,
        security_id=security_id,
        return_url=return_url,
        additional_infos=[add1, add2, add3, "NA", "NA", "NA", "NA"],
    )
    checksum = _billdesk_hmac_sha256(msg_without_checksum, encryption_key)
    request_msg = f"{msg_without_checksum}|{checksum}"

    # Pre-payment intent table (formerly eAbgari_Payment_Send_HOA).
    PaymentSendHOA.objects.update_or_create(
        transaction_id_no=transaction_id,
        head_of_account=LICENSE_FEE_HOA,
        defaults={
            "licensee_id": payer_id or None,
            "amount": amount,
            "payment_module_code": payment_module_code,
            "requisition_no": (_active_na_license_id_for_applicant(request.user) or "NA")[:50],
            "opr_date": timezone.now(),
        },
    )

    PaymentBilldeskTransaction.objects.update_or_create(
        utr=transaction_id,
        defaults={
            "transaction_date": timezone.now(),
            "transaction_id_no_hoa": transaction_id,
            "payer_id": payer_id,
            "payment_module_code": payment_module_code,
            "transaction_amount": amount,
            "request_merchantid": merchant_id,
            "request_currencytype": "INR",
            "request_typefield1": "R",
            "request_securityid": security_id,
            "request_typefield2": "F",
            "request_additionalinfo1": add1,
            "request_additionalinfo2": add2,
            "request_additionalinfo3": add3,
            "request_additionalinfo4": "NA",
            "request_additionalinfo5": "NA",
            "request_additionalinfo6": "NA",
            "request_additionalinfo7": "NA",
            "request_return_url": return_url,
            "request_checksum": checksum,
            "request_string": request_msg,
            "payment_status": "P",
            "opr_date": timezone.now(),
            "user_id": str(getattr(request.user, "username", "") or "").strip()[:50],
        },
    )

    return Response({"billdesk_url": billdesk_url, "request_msg": request_msg, "transaction_id": transaction_id})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def billdesk_initiate_security_deposit(request):
    """
    Security deposit (FDR) via BillDesk.

    As per payment logic document:
    - AdditionalInfo1: Licensee Name
    - AdditionalInfo2: SIKFDR
    - AdditionalInfo3: Bank/FDR code
    - AdditionalInfo4: Account holder full name (bank/FDR opening needs the name in the signed payload)
    - AdditionalInfo5: License Type
    - AdditionalInfo6: District
    """
    data = request.data or {}

    transaction_id = str(data.get("transaction_id") or "").strip() or _generate_transaction_id("SIKFDR")
    payer_id = str(data.get("payer_id") or data.get("licensee_id") or "").strip()[:50]
    licensee_name = str(data.get("licensee_name") or "").strip()
    account_holder_name = str(
        data.get("account_holder_name")
        or data.get("full_name")
        or data.get("customer_name")
        or ""
    ).strip()
    bank_fdr_code = str(data.get("bank_fdr_code") or data.get("fdr_code") or "SIKFDR").strip()
    license_type = str(data.get("license_type") or "").strip()
    district = str(data.get("district") or "").strip()
    # sems_payment_transaction_billdesk.payment_module_code must store a module_code from eabgari_master_module.
    payment_module_code = str(data.get("payment_module_code") or "").strip() or DEFAULT_LICENSE_RENEWAL_MODULE_CODE
    raw_amount = data.get("amount")

    if not payer_id:
        return Response({"detail": "licensee_id is required."}, status=status.HTTP_400_BAD_REQUEST)

    # Prefer explicit name passed from UI, else derive from authenticated user, else fallback.
    if not account_holder_name:
        account_holder_name = _build_full_name_from_user(getattr(request, "user", None))
    if not account_holder_name:
        account_holder_name = licensee_name or payer_id

    if not licensee_name:
        licensee_name = account_holder_name or payer_id

    try:
        payment_module_code = _validate_payment_module_code(payment_module_code)
    except Exception as exc:
        # Do not hard-block initiation if the master module table is missing/out-of-sync in an env.
        logger.warning(
            "Invalid payment_module_code=%s for security deposit initiation; proceeding with raw value. err=%s",
            payment_module_code,
            exc,
        )

    try:
        amount = _normalize_amount(raw_amount)
    except Exception as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    gateway = (
        PaymentGatewayParameters.objects.filter(is_active="Y", payment_gateway_name__iexact="Billdesk")
        .order_by("sl_no")
        .first()
    )
    if gateway is None:
        return Response(
            {"detail": "No active Billdesk configuration found in Payment_Gateway_Parameters."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if getattr(settings, "BILLDESK_USE_MOCK", False):
        billdesk_url = request.build_absolute_uri(reverse("payment_gateway:billdesk-mock-process"))
        return_url = request.build_absolute_uri(reverse("payment_gateway:billdesk-response"))
    else:
        billdesk_url = getattr(settings, "BILLDESK_GATEWAY_URL", "") or ""
        return_url = str(gateway.return_url or "").strip()

    if not billdesk_url:
        return Response({"detail": "BILLDESK_GATEWAY_URL is not configured on server."}, status=500)
    if not return_url:
        return Response({"detail": "return_url is not configured for Billdesk in Payment_Gateway_Parameters."}, status=500)

    merchant_id = str(gateway.merchantid or "").strip()
    security_id = str(gateway.securityid or "").strip()
    encryption_key = str(gateway.encryption_key or "").strip()
    if not merchant_id or not security_id or not encryption_key:
        return Response({"detail": "Billdesk gateway config is missing merchantid/securityid/encryption_key."}, status=500)

    amount_str = f"{amount:.2f}"
    add1 = account_holder_name or licensee_name
    add2 = "SIKFDR"
    add3 = bank_fdr_code or "SIKFDR"
    # Do not send license number in this field; bank requires full name for FDR opening.
    add4 = account_holder_name or licensee_name or payer_id
    add5 = license_type or "NA"
    add6 = district or "NA"
    # Do not send license number in signed payload fields for bank/FDR opening.
    # Licensee id is already stored in DB column `payer_id` for traceability.
    add7 = "NA"

    msg_without_checksum = _build_billdesk_request_message(
        merchant_id=merchant_id,
        transaction_id=transaction_id,
        amount_str=amount_str,
        security_id=security_id,
        return_url=return_url,
        additional_infos=[add1, add2, add3, add4, add5, add6, add7],
    )
    checksum = _billdesk_hmac_sha256(msg_without_checksum, encryption_key)
    request_msg = f"{msg_without_checksum}|{checksum}"

    PaymentSendHOA.objects.update_or_create(
        transaction_id_no=transaction_id,
        head_of_account=SECURITY_DEPOSIT_HOA_SENTINEL,
        defaults={
            "licensee_id": payer_id or None,
            "amount": amount,
            "payment_module_code": payment_module_code,
            "requisition_no": (_active_na_license_id_for_applicant(request.user) or "NA")[:50],
            "opr_date": timezone.now(),
        },
    )

    PaymentBilldeskTransaction.objects.update_or_create(
        utr=transaction_id,
        defaults={
            "transaction_date": timezone.now(),
            "transaction_id_no_hoa": transaction_id,
            "payer_id": payer_id,
            "payment_module_code": payment_module_code,
            "transaction_amount": amount,
            "request_merchantid": merchant_id,
            "request_currencytype": "INR",
            "request_typefield1": "R",
            "request_securityid": security_id,
            "request_typefield2": "F",
            "request_additionalinfo1": add1,
            "request_additionalinfo2": add2,
            "request_additionalinfo3": add3,
            "request_additionalinfo4": add4,
            "request_additionalinfo5": add5,
            "request_additionalinfo6": add6,
            "request_additionalinfo7": add7,
            "request_return_url": return_url,
            "request_checksum": checksum,
            "request_string": request_msg,
            "payment_status": "P",
            "opr_date": timezone.now(),
            "user_id": str(getattr(request.user, "username", "") or "").strip()[:50],
        },
    )

    return Response({"billdesk_url": billdesk_url, "request_msg": request_msg, "transaction_id": transaction_id})


@csrf_exempt
def billdesk_response(request):
    if request.method != "POST":
        return HttpResponseBadRequest("Invalid method")

    response_msg = str(request.POST.get("msg") or "").strip()
    if not response_msg:
        response_msg = str(request.POST.get("MSG") or "").strip()
    if not response_msg:
        return HttpResponseBadRequest("Missing msg")

    parts = response_msg.split("|")
    if len(parts) < 3:
        return HttpResponseBadRequest("Invalid msg format")

    response_checksum = parts[-1].strip()
    msg_without_checksum = "|".join(parts[:-1])

    # BillDesk response format (typical):
    # MerchantID|CustomerID|TxnReferenceNo|BankReferenceNo|TxnAmount|BankID|BankMerchantID|TxnType|CurrencyName|ItemCode|
    # SecurityType|SecurityID|SecurityPassword|TxnDate|AuthStatus|SettlementType|AdditionalInfo1..7|ErrorStatus|ErrorDescription|Checksum
    resp_merchantid = parts[0].strip() if len(parts) > 0 else ""
    resp_customerid = parts[1].strip() if len(parts) > 1 else ""
    txn_ref = parts[2].strip() if len(parts) > 2 else ""
    bank_ref = parts[3].strip() if len(parts) > 3 else ""
    resp_amount = parts[4].strip() if len(parts) > 4 else ""
    resp_bankid = parts[5].strip() if len(parts) > 5 else ""
    resp_bankmerchantid = parts[6].strip() if len(parts) > 6 else ""
    resp_txntype = parts[7].strip() if len(parts) > 7 else ""
    resp_currencyname = parts[8].strip() if len(parts) > 8 else ""
    resp_itemcode = parts[9].strip() if len(parts) > 9 else ""
    resp_securitytype = parts[10].strip() if len(parts) > 10 else ""
    resp_securityid = parts[11].strip() if len(parts) > 11 else ""
    resp_securitypassword = parts[12].strip() if len(parts) > 12 else ""
    resp_txndate_raw = parts[13].strip() if len(parts) > 13 else ""
    auth_status = parts[14].strip() if len(parts) > 14 else ""
    resp_settlementtype = parts[15].strip() if len(parts) > 15 else ""

    resp_additional = [parts[i].strip() if len(parts) > i else "" for i in range(16, 23)]
    error_status = parts[23].strip() if len(parts) > 23 else ""
    error_desc = parts[24].strip() if len(parts) > 24 else ""

    tx = None
    if txn_ref:
        tx = PaymentBilldeskTransaction.objects.filter(utr=txn_ref).first()
        if tx is None:
            tx = PaymentBilldeskTransaction.objects.filter(transaction_id_no_hoa=txn_ref).first()

    gateway = (
        PaymentGatewayParameters.objects.filter(is_active="Y", payment_gateway_name__iexact="Billdesk")
        .order_by("sl_no")
        .first()
    )
    encryption_key = str(getattr(gateway, "encryption_key", "") or "").strip()
    calculated_checksum = _billdesk_hmac_sha256(msg_without_checksum, encryption_key) if encryption_key else ""

    checksum_ok = bool(calculated_checksum and calculated_checksum.upper() == response_checksum.upper())
    if tx:
        try:
            parsed_amount = Decimal(str(resp_amount)).quantize(Decimal("0.01")) if resp_amount else None
        except Exception:
            parsed_amount = None

        status_code = "S" if auth_status == "0300" and checksum_ok else "F"
        tx.response_string = response_msg
        tx.response_merchantid = resp_merchantid or None
        tx.response_customerid = resp_customerid or None
        tx.response_txnreferenceno = txn_ref or None
        tx.response_bankreferenceno = bank_ref or None
        tx.response_txnamount = parsed_amount
        tx.response_bankid = resp_bankid or None
        tx.response_bankmerchantid = resp_bankmerchantid or None
        tx.response_txntype = resp_txntype or None
        tx.response_currencyname = resp_currencyname or None
        tx.response_itemcode = resp_itemcode or None
        tx.response_securitytype = resp_securitytype or None
        tx.response_securityid = resp_securityid or None
        tx.response_securitypassword = resp_securitypassword or None
        # Preserve raw string in case BillDesk changes date format.
        tx.response_txndate = None
        tx.response_authstatus = auth_status or None
        tx.response_settlementtype = resp_settlementtype or None
        tx.response_additionalinfo1 = resp_additional[0] or None
        tx.response_additionalinfo2 = resp_additional[1] or None
        tx.response_additionalinfo3 = resp_additional[2] or None
        tx.response_additionalinfo4 = resp_additional[3] or None
        tx.response_additionalinfo5 = resp_additional[4] or None
        tx.response_additionalinfo6 = resp_additional[5] or None
        tx.response_additionalinfo7 = resp_additional[6] or None
        tx.response_errorstatus = error_status or None
        tx.response_errordescription = error_desc or None
        tx.response_checksum = response_checksum or None
        tx.response_checksum_calculated = calculated_checksum or None
        tx.response_initial_authstatus = auth_status or None
        tx.response_initial_datetime = timezone.now()
        tx.payment_status = status_code
        tx.opr_date = timezone.now()
        tx.save()

        # Persist wallet_transactions entry for license fee / security deposit on successful payment.
        if status_code == "S":
            try:
                req_type = str(tx.request_additionalinfo2 or "").strip().upper()
                credit_licensee_id = ""
                credit_name = ""
                credit_wallet_type = ""
                credit_hoa = ""

                if req_type == "SIKPAY":
                    credit_licensee_id = str(tx.payer_id or "").strip()
                    credit_wallet_type = "license_fee"
                    credit_hoa = str(tx.request_additionalinfo1 or "").strip() or LICENSE_FEE_HOA
                elif req_type == "SIKFDR":
                    # For SIKFDR, AdditionalInfo4 stores the account holder name, not the licensee id.
                    credit_licensee_id = str(tx.payer_id or "").strip()
                    credit_name = str(tx.request_additionalinfo1 or "").strip()
                    credit_wallet_type = "security_deposit"
                    credit_hoa = SECURITY_DEPOSIT_HOA_SENTINEL
                else:
                    credit_licensee_id = str(tx.payer_id or "").strip()
                    credit_wallet_type = str(tx.request_additionalinfo3 or "").strip()
                    credit_hoa = str(tx.request_additionalinfo1 or "").strip() or "non"

                if credit_wallet_type and credit_licensee_id:
                    credit_wallet_balance(
                        transaction_id=str(txn_ref or tx.utr or "").strip(),
                        licensee_id=credit_licensee_id,
                        wallet_type=credit_wallet_type,
                        head_of_account=credit_hoa,
                        amount=parsed_amount or Decimal(str(tx.transaction_amount or 0)).quantize(Decimal("0.01")),
                        user_id=str(tx.user_id or "").strip(),
                        licensee_name=credit_name,
                        source_module="wallet_recharge",
                        transaction_type="recharge",
                        remarks="BillDesk payment success",
                    )
            except Exception as exc:
                logger.exception("Failed to credit wallet for txn_ref=%s: %s", txn_ref, exc)
        elif status_code == "F":
            try:
                req_type = str(tx.request_additionalinfo2 or "").strip().upper()
                log_licensee_id = ""
                log_name = ""
                log_wallet_type = ""
                log_hoa = ""

                if req_type == "SIKPAY":
                    log_licensee_id = str(tx.payer_id or "").strip()
                    log_wallet_type = "license_fee"
                    log_hoa = str(tx.request_additionalinfo1 or "").strip() or LICENSE_FEE_HOA
                elif req_type == "SIKFDR":
                    log_licensee_id = str(tx.payer_id or "").strip()
                    log_name = str(tx.request_additionalinfo1 or "").strip()
                    log_wallet_type = "security_deposit"
                    log_hoa = SECURITY_DEPOSIT_HOA_SENTINEL
                else:
                    log_licensee_id = str(tx.payer_id or "").strip()
                    log_wallet_type = str(tx.request_additionalinfo3 or "").strip()
                    log_hoa = str(tx.request_additionalinfo1 or "").strip() or "non"

                fail_reason = str(error_desc or "").strip() or ("checksum_mismatch" if not checksum_ok else "failed")

                if log_wallet_type and log_licensee_id:
                    record_wallet_transaction(
                        transaction_id=str(txn_ref or tx.utr or "").strip(),
                        licensee_id=log_licensee_id,
                        wallet_type=log_wallet_type,
                        head_of_account=log_hoa,
                        amount=parsed_amount or Decimal(str(tx.transaction_amount or 0)).quantize(Decimal("0.01")),
                        user_id=str(tx.user_id or "").strip(),
                        licensee_name=log_name,
                        source_module="wallet_recharge",
                        transaction_type="recharge",
                        payment_status="failed",
                        remarks=f"BillDesk payment failed: {fail_reason}",
                    )
            except Exception as exc:
                logger.exception("Failed to log failed wallet transaction for txn_ref=%s: %s", txn_ref, exc)

    gateway = (
        PaymentGatewayParameters.objects.filter(is_active="Y", payment_gateway_name__iexact="Billdesk")
        .order_by("sl_no")
        .first()
    )
    frontend_success = str(getattr(gateway, "frontend_success_url", "") or "").strip()
    if not frontend_success:
        frontend_success = str(getattr(settings, "PAYMENT_GATEWAY_FRONTEND_SUCCESS_URL", "") or "").strip()
    if not frontend_success:
        return HttpResponseBadRequest(
            "Frontend success URL not configured (set Payment_Gateway_Parameters.frontend_success_url or PAYMENT_GATEWAY_FRONTEND_SUCCESS_URL)."
        )

    if tx:
        req_type = str(tx.request_additionalinfo2 or "").strip().upper()
        if req_type == "SIKPAY":
            wallet_type = "license_fee"
            hoa = str(tx.request_additionalinfo1 or "").strip()
        elif req_type == "SIKFDR":
            wallet_type = "security_deposit"
            hoa = SECURITY_DEPOSIT_HOA_SENTINEL
        else:
            wallet_type = str(tx.request_additionalinfo3 or "").strip()
            hoa = str(tx.request_additionalinfo1 or "").strip()
        amt = f"{Decimal(str(tx.transaction_amount or 0)).quantize(Decimal('0.01')):.2f}"
        created_at = tx.transaction_date.isoformat() if tx.transaction_date else ""
    else:
        wallet_type = ""
        hoa = ""
        amt = resp_amount or ""
        created_at = ""

    ui_status = "success" if auth_status == "0300" and checksum_ok else "failed"
    ui_reason = ""
    if ui_status != "success":
        ui_reason = str(error_desc or "").strip() or ("checksum_mismatch" if not checksum_ok else "failed")
    query = urlencode(
        {
            "transactionId": txn_ref,
            "walletType": wallet_type,
            "hoa": hoa,
            "amount": amt,
            "status": ui_status,
            "reason": ui_reason,
            "createdAt": created_at,
            "additionalInfo2": str(getattr(tx, "request_additionalinfo2", "") or "").strip() if tx else "",
            "additionalInfo3": str(getattr(tx, "request_additionalinfo3", "") or "").strip() if tx else "",
        }
    )
    return redirect(f"{frontend_success}?{query}")


@csrf_exempt
def billdesk_mock_process(request):
    """
    Localhost testing helper.

    The Angular app auto-POSTs `msg=<request_msg>` to the BillDesk gateway URL.
    When BILLDESK_USE_MOCK=1, our initiate endpoint returns this mock URL instead.

    This endpoint simulates BillDesk's ProcessPayment by generating a response `msg`
    (with checksum) and auto-POSTing it to our `/billdesk/response/` handler.
    """
    if request.method != "POST":
        return HttpResponseBadRequest("Invalid method")

    incoming = str(request.POST.get("msg") or request.POST.get("MSG") or "").strip()
    if not incoming:
        return HttpResponseBadRequest("Missing msg")

    req_parts = incoming.split("|")
    if len(req_parts) < 5:
        return HttpResponseBadRequest("Invalid request msg format")

    merchant_id = req_parts[0].strip()
    txn_ref = req_parts[1].strip()
    amount = req_parts[3].strip()

    gateway = (
        PaymentGatewayParameters.objects.filter(is_active="Y", payment_gateway_name__iexact="Billdesk")
        .order_by("sl_no")
        .first()
    )
    encryption_key = str(getattr(gateway, "encryption_key", "") or "").strip()
    if not encryption_key:
        return HttpResponseBadRequest("Missing encryption key")

    auth_status = str(getattr(settings, "BILLDESK_MOCK_AUTH_STATUS", "0300") or "0300").strip()
    error_status = "NA" if auth_status == "0300" else "ERR"
    error_desc = "NA" if auth_status == "0300" else "MOCK_FAILED"

    # Build a realistic BillDesk response string (checksum appended at end).
    # MerchantID|CustomerID|TxnReferenceNo|BankReferenceNo|TxnAmount|BankID|BankMerchantID|TxnType|CurrencyName|ItemCode|
    # SecurityType|SecurityID|SecurityPassword|TxnDate|AuthStatus|SettlementType|AdditionalInfo1..7|ErrorStatus|ErrorDescription|Checksum
    customer_id = "NA"
    bank_ref = f"MOCK{timezone.now().strftime('%Y%m%d%H%M%S')}"
    bank_id = "NA"
    bank_merchant_id = "NA"
    txn_type = "NA"
    currency = "INR"
    item_code = "NA"
    security_type = "NA"
    security_id = str(getattr(gateway, "securityid", "") or "").strip() or "NA"
    security_password = "NA"
    txn_date = timezone.now().strftime("%Y-%m-%d %H:%M:%S")
    settlement_type = "NA"

    # Try to echo back additional info from our stored request (if present).
    tx = PaymentBilldeskTransaction.objects.filter(utr=txn_ref).first()
    add = [
        str(getattr(tx, "request_additionalinfo1", "") or "NA"),
        str(getattr(tx, "request_additionalinfo2", "") or "NA"),
        str(getattr(tx, "request_additionalinfo3", "") or "NA"),
        str(getattr(tx, "request_additionalinfo4", "") or "NA"),
        str(getattr(tx, "request_additionalinfo5", "") or "NA"),
        str(getattr(tx, "request_additionalinfo6", "") or "NA"),
        str(getattr(tx, "request_additionalinfo7", "") or "NA"),
    ]

    resp_without_checksum = (
        f"{merchant_id}|{customer_id}|{txn_ref}|{bank_ref}|{amount}|{bank_id}|{bank_merchant_id}|{txn_type}|"
        f"{currency}|{item_code}|{security_type}|{security_id}|{security_password}|{txn_date}|{auth_status}|"
        f"{settlement_type}|{add[0]}|{add[1]}|{add[2]}|{add[3]}|{add[4]}|{add[5]}|{add[6]}|{error_status}|{error_desc}"
    )
    resp_checksum = _billdesk_hmac_sha256(resp_without_checksum, encryption_key)
    response_msg = f"{resp_without_checksum}|{resp_checksum}"

    fail_auth_status = "0399"
    fail_error_status = "ERR"
    fail_error_desc = "MOCK_FAILED"
    resp_without_checksum_fail = (
        f"{merchant_id}|{customer_id}|{txn_ref}|{bank_ref}|{amount}|{bank_id}|{bank_merchant_id}|{txn_type}|"
        f"{currency}|{item_code}|{security_type}|{security_id}|{security_password}|{txn_date}|{fail_auth_status}|"
        f"{settlement_type}|{add[0]}|{add[1]}|{add[2]}|{add[3]}|{add[4]}|{add[5]}|{add[6]}|{fail_error_status}|{fail_error_desc}"
    )
    resp_checksum_fail = _billdesk_hmac_sha256(resp_without_checksum_fail, encryption_key)
    response_msg_fail = f"{resp_without_checksum_fail}|{resp_checksum_fail}"

    callback_url = reverse("payment_gateway:billdesk-response")

    escaped_msg = html.escape(response_msg, quote=True)
    escaped_msg_fail = html.escape(response_msg_fail, quote=True)
    escaped_txn = html.escape(txn_ref, quote=True)
    escaped_amount = html.escape(amount, quote=True)
    escaped_status = html.escape(auth_status, quote=True)

    # Show a simple BillDesk-like page so testers can actually "see" the payment step.
    page = f"""
<!doctype html>
<html>
  <head>
    <meta charset="utf-8">
    <title>BillDesk Mock Payment</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
      body {{ font-family: Arial, sans-serif; margin: 24px; background: #f6f7fb; }}
      .card {{ max-width: 720px; margin: 0 auto; background: #fff; border: 1px solid #e6e8f0; border-radius: 10px; padding: 18px 18px 14px; }}
      .hdr {{ font-size: 18px; font-weight: 700; margin-bottom: 8px; }}
      .sub {{ color: #556; margin-bottom: 18px; }}
      .row {{ display: flex; gap: 12px; margin: 8px 0; }}
      .k {{ width: 220px; color: #334; font-weight: 600; }}
      .v {{ flex: 1; color: #111; word-break: break-all; }}
      .btns {{ display: flex; gap: 10px; margin-top: 18px; }}
      button {{ border: 0; border-radius: 8px; padding: 10px 14px; cursor: pointer; font-weight: 700; }}
      .pay {{ background: #16a34a; color: #fff; }}
      .fail {{ background: #dc2626; color: #fff; }}
      .note {{ margin-top: 14px; color: #667; font-size: 12px; }}
    </style>
  </head>
  <body>
    <div class="card">
      <div class="hdr">BillDesk Mock Payment Page</div>
      <div class="sub">This page is shown only when <code>BILLDESK_USE_MOCK=1</code> for localhost testing.</div>

      <div class="row"><div class="k">Transaction</div><div class="v">{escaped_txn}</div></div>
      <div class="row"><div class="k">Amount</div><div class="v">{escaped_amount}</div></div>
      <div class="row"><div class="k">AuthStatus (mock)</div><div class="v">{escaped_status}</div></div>

      <div class="btns">
        <form method="POST" action="{callback_url}">
          <input type="hidden" name="msg" value="{escaped_msg}">
          <button type="submit" class="pay">Pay (Post Response)</button>
        </form>
        <form method="POST" action="{callback_url}">
          <input type="hidden" name="msg" value="{escaped_msg_fail}">
          <button type="submit" class="fail">Fail</button>
        </form>
      </div>

      <div class="note">Tip: set <code>BILLDESK_MOCK_AUTH_STATUS</code> to control the default success status (0300).</div>
    </div>
  </body>
</html>
""".strip()
    return HttpResponse(page, content_type="text/html")
