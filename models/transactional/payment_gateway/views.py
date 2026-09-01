import logging
from decimal import Decimal
import secrets
from datetime import timedelta
import json
import base64
import time
from django.db import transaction
try:
    import requests
except ModuleNotFoundError:
    requests = None
from excise_backend.settings import BILLDESK_GATEWAY_URL
from .billdesk_utils import (
    decrypt_and_verify_billdesk_response,
    generate_billdesk_nested_jose,
)
from django.conf import settings
from django.db.utils import OperationalError, ProgrammingError
from django.http import HttpResponse, HttpResponseBadRequest, request
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.urls import reverse
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from models.transactional.new_license_application.models import NewLicenseApplication
from auth.user.models import CustomUser
from .models import PaymentBilldeskTransaction, PaymentGatewayParameters, PaymentSendHOA, MasterPaymentModule
from models.transactional.wallet.wallet_service import credit_wallet_balance, record_wallet_transaction
from models.transactional.wallet.models import _resolve_wallet_row_licensee_id
from models.transactional.wallet.models import WalletBalance

logger = logging.getLogger(__name__)

LICENSE_FEE_HOA = "0039-00-800-45-02"
SECURITY_DEPOSIT_HOA_SENTINEL = "non"
DEFAULT_LICENSE_RENEWAL_MODULE_CODE = "002"
DEFAULT_WALLET_ADVANCE_MODULE_CODE = "999"
DEFAULT_NEW_LICENSE_APPLICATION_MODULE_CODE = "001"
PENDING_RETRY_LOCK_MINUTES = 1

def _build_pending_retry_response(tx: PaymentBilldeskTransaction, remaining_seconds: int) -> Response:
    lock_until = (tx.transaction_date or timezone.now()) + timedelta(minutes=PENDING_RETRY_LOCK_MINUTES)
    return Response(
        {
            "detail": "A BillDesk payment is already pending. Please try again after 15 minutes.",
            "status": "pending",
            "pending_transaction_id": str(getattr(tx, "utr", "") or getattr(tx, "transaction_id_no_hoa", "") or "").strip(),
            "retry_after_seconds": int(max(0, remaining_seconds)),
            "retry_after": lock_until.isoformat(),
        },
        status=status.HTTP_409_CONFLICT,
    )


def _recent_pending_for_payer(payer_id: str) -> PaymentBilldeskTransaction | None:
    pid = str(payer_id or "").strip()
    if not pid:
        return None
    cutoff = timezone.now() - timedelta(minutes=PENDING_RETRY_LOCK_MINUTES)
    return (
        PaymentBilldeskTransaction.objects.filter(
            payer_id__iexact=pid,
            payment_status__iexact="P",
            transaction_date__gte=cutoff,
        )
        .order_by("-transaction_date")
        .first()
    )


def _normalize_wallet_type(wallet_type: str) -> str:
    value = str(wallet_type or "").strip().lower().replace(" ", "_").replace("-", "_")
    if value in {"education", "educationcess", "education_cess", "educationcesswallet", "education_cess_wallet"}:
        return "education_cess"
    if value in {"excise", "excise_duty", "excise_duty_wallet", "exciseduty", "excise_wallet"}:
        return "excise"
    return value


def _resolve_wallet_head_of_account(*, licensee_id: str, wallet_type: str, user_id: str = "") -> str:

    # Resolve Head Of Account for wallet recharge initiation.

    lid = str(licensee_id or "").strip()
    wtype = str(wallet_type or "").strip()
    uid = str(user_id or "").strip()
    if not lid or not wtype:
        return ""
    try:
        resolved_lid = _resolve_wallet_row_licensee_id(lid, uid) or lid
        qs = (
            WalletBalance.objects.filter(
                licensee_id__iexact=resolved_lid,
                wallet_type__code__iexact=wtype,
            )
            .order_by("wallet_balance_id")
        )
        row = qs.exclude(head_of_account__isnull=True).exclude(head_of_account__exact="").exclude(head_of_account__iexact="non").first()
        if not row:
            row = qs.first()
        return str(getattr(row, "head_of_account", "") or "").strip()
    except Exception:
        return ""


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


def _normalize_amount(raw_amount) -> Decimal:
    value = Decimal(str(raw_amount or "0")).quantize(Decimal("0.01"))
    if value <= 0:
        raise ValueError("amount must be greater than zero")
    return value


def _validate_payment_module_code(module_code: str) -> str:
    code = str(module_code or "").strip()
    if not code:
        raise ValueError("payment_module_code is required.")

    try:
        if MasterPaymentModule.objects.filter(module_code=code).exists():
            return code
    except (OperationalError, ProgrammingError):
        pass

    try:
        from models.masters.core.models import MasterFixedFee
        if MasterFixedFee.objects.filter(fee_code=code).exists():
            return code
    except Exception:
        pass

    raise ValueError(f"Invalid payment_module_code={code}. Not found in master module table or fixed fee table.")


def _get_module_license_fee(module_code: str) -> Decimal | None:
    code = str(module_code or "").strip()
    if not code:
        return None
    try:
        module = (
            MasterPaymentModule.objects
            .only("module_code", "license_fee")
            .filter(module_code=code)
            .first()
        )
        fee = getattr(module, "license_fee", None) if module else None
        if fee in (None, ""):
            from models.masters.core.models import MasterFixedFee
            fixed_fee = MasterFixedFee.objects.filter(fee_code=code).first()
            fee = getattr(fixed_fee, "amount", None) if fixed_fee else None

        if fee in (None, ""):
            return None
        return _normalize_amount(fee)
    except Exception:
        return None


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_payment_module(request, module_code: str):
    code = str(module_code or "").strip()
    if not code:
        return Response({"detail": "module_code is required."}, status=status.HTTP_400_BAD_REQUEST)

    module = MasterPaymentModule.objects.filter(module_code=code).first()
    if not module:
        from models.masters.core.models import MasterFixedFee
        fixed_fee = MasterFixedFee.objects.filter(fee_code=code).first()
        if not fixed_fee:
            return Response({"detail": f"Module not found for module_code={code}."}, status=status.HTTP_404_NOT_FOUND)
        
        fee = getattr(fixed_fee, "amount", None)
        try:
            if fee not in (None, ""):
                fee = _normalize_amount(fee)
        except Exception:
            fee = None

        return Response(
            {
                "module_code": str(getattr(fixed_fee, "fee_code", "") or "").strip(),
                "module_desc": str(getattr(fixed_fee, "fee_desc", "") or "").strip(),
                "license_fee": float(fee) if fee is not None else None,
            }
        )

    fee = None
    try:
        raw_fee = getattr(module, "license_fee", None)
        if raw_fee not in (None, ""):
            fee = _normalize_amount(raw_fee)
    except Exception:
        fee = None

    return Response(
        {
            "module_code": str(getattr(module, "module_code", "") or "").strip(),
            "module_desc": str(getattr(module, "module_desc", "") or "").strip(),
            "license_fee": float(fee) if fee is not None else None,
        }
    )


def _generate_transaction_id(prefix: str = "TXN") -> str:
    return f"{prefix}{timezone.now().strftime('%Y%m%d%H%M%S')}{secrets.token_hex(4).upper()}"


def _decode_jws_payload(jws_token: str) -> dict:
    """Decodes the Base64URL payload of a JWS token into a Python dictionary."""
    parts = jws_token.split('.')
    if len(parts) != 3:
        return {}
    payload_b64 = parts[1]
    missing = (-len(payload_b64)) % 4
    padding = '=' * missing
    payload_json = base64.urlsafe_b64decode(payload_b64 + padding).decode('utf-8')
    return json.loads(payload_json)

def _create_billdesk_order(
    merchant_id,
    client_id,
    secret_key,
    tx_id,
    amount_str,
    return_url,
    additional_info_dict,
    request,
    device_data=None,
):
  if device_data is None:
    device_data = {}

  x_real_ip = request.META.get('HTTP_X_REAL_IP')
  x_cf_ip = request.META.get('HTTP_CF_CONNECTING_IP')
  x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
  if x_cf_ip:
    client_ip = x_cf_ip.split(',')[0].strip()
  elif x_real_ip:
    client_ip = x_real_ip.split(',')[0].strip()
  elif x_forwarded_for:
    client_ip = x_forwarded_for.split(',')[0].strip()
  else:
    client_ip = request.META.get('REMOTE_ADDR', '127.0.0.1')

  order_date = timezone.localtime(timezone.now()).strftime("%Y-%m-%dT%H:%M:%S+05:30")

  payload = {
      "mercid": merchant_id,
      "orderid": tx_id,
      "amount": amount_str,
      "order_date": order_date,
      "currency": "356",
      "ru": return_url,
      "itemcode": "DIRECT",
      "additional_info": additional_info_dict,
      "device": {
          "init_channel": "internet",
          "ip": client_ip,
          "user_agent": (
              device_data.get("user_agent")
              or request.META.get("HTTP_USER_AGENT", "Mozilla/5.0")[:250]
          ),
          "accept_header": device_data.get("accept_header", "text/html"),
          "browser_tz": str(device_data.get("browser_tz", "-330")),
          "browser_color_depth": str(
              device_data.get("browser_color_depth", "32")
          ),
          "browser_java_enabled": str(
              device_data.get("browser_java_enabled", "false")
          ).lower(),
          "browser_screen_height": str(
              device_data.get("browser_screen_height", "1080")
          ),
          "browser_screen_width": str(
              device_data.get("browser_screen_width", "1920")
          ),
          "browser_language": device_data.get("browser_language", "en-US"),
          "browser_javascript_enabled": str(
              device_data.get("browser_javascript_enabled", "true")
          ).lower(),
      },
  }

  nested_jose_token = generate_billdesk_nested_jose(client_id, payload)

  headers = {
        "Content-Type": "application/jose",
        "Accept": "application/jose",
        "BD-Traceid": tx_id,
        "BD-Timestamp": str(int(timezone.now().timestamp() * 1000))
    }

  api_url = BILLDESK_GATEWAY_URL

  response = requests.post(api_url, data=nested_jose_token, headers=headers)

  if response.status_code == 200:
    resp_data = decrypt_and_verify_billdesk_response(response.text)
    bdorderid = resp_data.get("bdorderid")
    auth_token = None

    for link in resp_data.get("links", []):
      if link.get("rel") == "redirect":
        auth_token = link.get("headers", {}).get("authorization")
        break

    return {
        "success": True,
        "bdorderid": bdorderid,
        "rdata": auth_token,
        "authorization": auth_token,
        "merchant_id": merchant_id,
        "request_string": nested_jose_token,
    }
  else:
    logger.error(f"BillDesk Create Order Failed: {response.text}")
    error_details = response.text
    try:
      error_details = decrypt_and_verify_billdesk_response(response.text)
    except Exception:
      pass
    return {"success": False, "error": error_details}

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
    for key in ("name", "full_name", "fullname"):
        value = str(getattr(user, key, "") or "").strip()
        if value:
            return value
    return ""


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def billdesk_initiate_wallet_recharge(request):
    data = request.data or {}
    device_data = data.get("device_data", {})
    transaction_id = str(data.get("transaction_id") or "").strip()
    wallet_type = _normalize_wallet_type(data.get("wallet_type"))
    licensee_id = str(data.get("licensee_id") or data.get("licenseeId") or "").strip()[:50]
    head_of_account = str(data.get("head_of_account") or "").strip()
    payment_module_code = str(data.get("payment_module_code") or "").strip()
    payer_id = str(data.get("payer_id") or getattr(request.user, "username", "") or "").strip()[:50]
    raw_amount = data.get("amount")

    if not transaction_id:
        return Response({"detail": "transaction_id is required."}, status=status.HTTP_400_BAD_REQUEST)
    if not wallet_type:
        return Response({"detail": "wallet_type is required."}, status=status.HTTP_400_BAD_REQUEST)

    if not licensee_id:
        licensee_id = str(_active_na_license_id_for_applicant(request.user) or "").strip()[:50]

    resolved_hoa = ""
    if licensee_id:
        resolved_hoa = _resolve_wallet_head_of_account(
            licensee_id=licensee_id,
            wallet_type=wallet_type,
            user_id=str(getattr(request.user, "username", "") or "").strip(),
        )
    if resolved_hoa:
        head_of_account = resolved_hoa
    if not head_of_account:
        return Response(
            {
                "detail": "head_of_account could not be resolved for the selected wallet.",
                "wallet_type": wallet_type,
                "licensee_id": licensee_id or None,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    if payment_module_code:
        try:
            payment_module_code = _validate_payment_module_code(payment_module_code)
        except Exception:
            logger.warning("Unknown payment_module_code=%s for wallet recharge; storing as-is.", payment_module_code)
    else:
        payment_module_code = DEFAULT_WALLET_ADVANCE_MODULE_CODE
        try:
            payment_module_code = _validate_payment_module_code(payment_module_code)
        except Exception:
            payment_module_code = DEFAULT_WALLET_ADVANCE_MODULE_CODE

    try:
        amount = _normalize_amount(raw_amount)
    except Exception as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    pending_tx = _recent_pending_for_payer(payer_id)
    if pending_tx:
        existing_txn_id = str(getattr(pending_tx, "utr", "") or getattr(pending_tx, "transaction_id_no_hoa", "") or "").strip()
        if existing_txn_id and existing_txn_id == transaction_id and str(getattr(pending_tx, "request_string", "") or "").strip():
            if getattr(settings, "BILLDESK_USE_MOCK", False):
                billdesk_url = request.build_absolute_uri(reverse("payment_gateway:billdesk-mock-process"))
            else:
                billdesk_url = getattr(settings, "BILLDESK_GATEWAY_URL", "") or ""
            return Response(
                {
                    "billdesk_url": billdesk_url,
                    "request_msg": str(pending_tx.request_string).strip(),
                    "transaction_id": existing_txn_id,
                    "already_pending": True,
                }
            )

        lock_until = (pending_tx.transaction_date or timezone.now()) + timedelta(minutes=PENDING_RETRY_LOCK_MINUTES)
        remaining = int(max(0, (lock_until - timezone.now()).total_seconds()))
        if remaining > 0:
            return _build_pending_retry_response(pending_tx, remaining)

    gateway = (
        PaymentGatewayParameters.objects.filter(is_active=True, payment_gateway_name__iexact="Billdesk")
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
    encryption_key = str(getattr(settings, "BILLDESK_ENCRYPTION_KEY", "") or getattr(gateway, "encryption_key", "") or "").strip()
    if not merchant_id or not security_id or not encryption_key:
        return Response(
            {"detail": "Billdesk gateway config is missing merchantid/securityid/encryption_key."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    amount_str = f"{amount:.2f}"

    client_id = merchant_id.lower() 
    
    additional_info_dict = {
        "additional_info1": head_of_account,
        "additional_info2": "WALLET",
        "additional_info3": wallet_type,
        "additional_info4": "NA",
        "additional_info5": "NA",
        "additional_info6": "NA",
        "additional_info7": "NA",
    }

    api_result = _create_billdesk_order(
        merchant_id=merchant_id,
        client_id=client_id,
        secret_key=encryption_key,
        tx_id=transaction_id,
        amount_str=amount_str,
        return_url=return_url,
        additional_info_dict=additional_info_dict,
        request=request,
        device_data=device_data
    )

    if not api_result.get("success"):
        return Response({"detail": "Failed to initiate transaction with gateway.", "error": api_result.get("error")}, status=status.HTTP_502_BAD_GATEWAY)

    bd_order_id = api_result["bdorderid"]
    auth_token = api_result["authorization"]
    request_msg = api_result["request_string"]

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
            "request_additionalinfo1": head_of_account,
            "request_additionalinfo2": "WALLET",
            "request_additionalinfo3": wallet_type,
            "request_additionalinfo4": "NA",
            "request_additionalinfo5": "NA",
            "request_additionalinfo6": "NA",
            "request_additionalinfo7": "NA",
            "request_return_url": return_url,
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
            "licensee_id": str(licensee_id or payer_id or "").strip()[:50] or None,
            "amount": amount,
            "payment_module_code": payment_module_code,
            "requisition_no": (_active_na_license_id_for_applicant(request.user) or "NA")[:50],
            "opr_date": timezone.now(),
        },
    )

    try:
        record_wallet_transaction(
            transaction_id=transaction_id,
            licensee_id=str(licensee_id or payer_id or "").strip()[:50] or payer_id,
            wallet_type=wallet_type,
            head_of_account=head_of_account,
            amount=amount,
            entry_type="CR",
            transaction_type="recharge",
            user_id=str(getattr(request.user, "username", "") or "").strip(),
            source_module="wallet_recharge",
            payment_status="pending",
            remarks="BillDesk payment initiated",
        )
    except Exception as exc:
        logger.warning("Failed to record pending wallet transaction for txn_id=%s: %s", transaction_id, exc)

    return Response(
        {
            "bd_order_id": bd_order_id,
            "auth_token": auth_token,
            "merchant_id": merchant_id,
            "transaction_id": transaction_id,
            "request_msg": request_msg,
        }
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def billdesk_initiate_license_fee(request):
    
    data = request.data or {}
    device_data = data.get("device_data", {})

    transaction_id = str(data.get("transaction_id") or "").strip() or _generate_transaction_id("SIKPAY")
    payer_id = str(data.get("payer_id") or data.get("licensee_id") or "").strip()[:50]
    payment_module_code = str(data.get("payment_module_code") or "").strip() or DEFAULT_LICENSE_RENEWAL_MODULE_CODE
    raw_amount = data.get("amount")

    if not payer_id:
        return Response({"detail": "licensee id is required."}, status=status.HTTP_400_BAD_REQUEST)

    try:
        payment_module_code = _validate_payment_module_code(payment_module_code)
    except Exception as exc:
        logger.warning(
            "Invalid payment_module_code=%s for license fee initiation; proceeding with raw value. err=%s",
            payment_module_code,
            exc,
        )

    try:
        amount = _normalize_amount(raw_amount)
    except Exception as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    pending_tx = _recent_pending_for_payer(payer_id)
    if pending_tx:
        existing_txn_id = str(getattr(pending_tx, "utr", "") or getattr(pending_tx, "transaction_id_no_hoa", "") or "").strip()
        if existing_txn_id and existing_txn_id == transaction_id and str(getattr(pending_tx, "request_string", "") or "").strip():
            if getattr(settings, "BILLDESK_USE_MOCK", False):
                billdesk_url = request.build_absolute_uri(reverse("payment_gateway:billdesk-mock-process"))
            else:
                billdesk_url = getattr(settings, "BILLDESK_GATEWAY_URL", "") or ""
            return Response(
                {
                    "billdesk_url": billdesk_url,
                    "request_msg": str(pending_tx.request_string).strip(),
                    "transaction_id": existing_txn_id,
                    "already_pending": True,
                }
            )

        lock_until = (pending_tx.transaction_date or timezone.now()) + timedelta(minutes=PENDING_RETRY_LOCK_MINUTES)
        remaining = int(max(0, (lock_until - timezone.now()).total_seconds()))
        if remaining > 0:
            return _build_pending_retry_response(pending_tx, remaining)

    gateway = (
        PaymentGatewayParameters.objects.filter(is_active=True, payment_gateway_name__iexact="Billdesk")
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
    encryption_key = str(getattr(settings, "BILLDESK_ENCRYPTION_KEY", "") or getattr(gateway, "encryption_key", "") or "").strip()
    if not merchant_id or not security_id or not encryption_key:
        return Response({"detail": "Billdesk gateway config is missing merchantid/securityid/encryption_key."}, status=500)

    amount_str = f"{amount:.2f}"
    
    additional_info_dict = {
        "additional_info1": LICENSE_FEE_HOA,
        "additional_info2": "SIKPAY",
        "additional_info3": "SIKPAY",
        "additional_info4": "NA",
        "additional_info5": "NA",
        "additional_info6": "NA",
        "additional_info7": "NA",
    }

    api_result = _create_billdesk_order(
        merchant_id=merchant_id,
        client_id=merchant_id.lower(),
        secret_key=encryption_key,
        tx_id=transaction_id,
        amount_str=amount_str,
        return_url=return_url,
        additional_info_dict=additional_info_dict,
        request=request,
        device_data=device_data
    )

    if not api_result.get("success"):
        return Response({"detail": "Failed to initiate transaction with gateway.", "error": api_result.get("error")}, status=status.HTTP_502_BAD_GATEWAY)

    bd_order_id = api_result["bdorderid"]
    auth_token = api_result["authorization"]
    request_msg = api_result["request_string"]

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
            "request_additionalinfo1": LICENSE_FEE_HOA,
            "request_additionalinfo2": "SIKPAY",
            "request_additionalinfo3": "SIKPAY",
            "request_additionalinfo4": "NA",
            "request_additionalinfo5": "NA",
            "request_additionalinfo6": "NA",
            "request_additionalinfo7": "NA",
            "request_return_url": return_url,
            "request_string": request_msg,
            "payment_status": "P",
            "opr_date": timezone.now(),
            "user_id": str(getattr(request.user, "username", "") or "").strip()[:50],
        },
    )

    try:
        record_wallet_transaction(
            transaction_id=transaction_id,
            licensee_id=payer_id,
            wallet_type="license_fee",
            head_of_account=LICENSE_FEE_HOA,
            amount=amount,
            entry_type="CR",
            transaction_type="recharge",
            user_id=str(getattr(request.user, "username", "") or "").strip(),
            source_module="wallet_recharge",
            payment_status="pending",
            remarks="BillDesk payment initiated",
        )
    except Exception as exc:
        logger.warning("Failed to record pending license fee transaction for txn_id=%s: %s", transaction_id, exc)

    return Response(
        {
            "bd_order_id": bd_order_id,
            "auth_token": auth_token,
            "merchant_id": merchant_id,
            "transaction_id": transaction_id,
            "request_msg": request_msg
        }
    )

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def billdesk_initiate_security_deposit(request):
    
    data = request.data or {}
    device_data = data.get("device_data", {})

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
    payment_module_code = str(data.get("payment_module_code") or "").strip() or DEFAULT_LICENSE_RENEWAL_MODULE_CODE
    raw_amount = data.get("amount")

    if not payer_id:
        return Response({"detail": "licensee id is required."}, status=status.HTTP_400_BAD_REQUEST)

    if not account_holder_name:
        account_holder_name = _build_full_name_from_user(getattr(request, "user", None))
    if not account_holder_name:
        account_holder_name = licensee_name or payer_id

    if not licensee_name:
        licensee_name = account_holder_name or payer_id

    try:
        payment_module_code = _validate_payment_module_code(payment_module_code)
    except Exception as exc:
        logger.warning(
            "Invalid payment_module_code=%s for security deposit initiation; proceeding with raw value. err=%s",
            payment_module_code,
            exc,
        )

    try:
        amount = _normalize_amount(raw_amount)
    except Exception as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    pending_tx = _recent_pending_for_payer(payer_id)
    if pending_tx:
        existing_txn_id = str(getattr(pending_tx, "utr", "") or getattr(pending_tx, "transaction_id_no_hoa", "") or "").strip()
        if existing_txn_id and existing_txn_id == transaction_id and str(getattr(pending_tx, "request_string", "") or "").strip():
            if getattr(settings, "BILLDESK_USE_MOCK", False):
                billdesk_url = request.build_absolute_uri(reverse("payment_gateway:billdesk-mock-process"))
            else:
                billdesk_url = getattr(settings, "BILLDESK_GATEWAY_URL", "") or ""
            return Response(
                {
                    "billdesk_url": billdesk_url,
                    "request_msg": str(pending_tx.request_string).strip(),
                    "transaction_id": existing_txn_id,
                    "already_pending": True,
                }
            )

        lock_until = (pending_tx.transaction_date or timezone.now()) + timedelta(minutes=PENDING_RETRY_LOCK_MINUTES)
        remaining = int(max(0, (lock_until - timezone.now()).total_seconds()))
        if remaining > 0:
            return _build_pending_retry_response(pending_tx, remaining)

    gateway = (
        PaymentGatewayParameters.objects.filter(is_active=True, payment_gateway_name__iexact="Billdesk")
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
    encryption_key = str(getattr(settings, "BILLDESK_ENCRYPTION_KEY", "") or getattr(gateway, "encryption_key", "") or "").strip()
    if not merchant_id or not security_id or not encryption_key:
        return Response({"detail": "Billdesk gateway config is missing merchantid/securityid/encryption_key."}, status=500)

    amount_str = f"{amount:.2f}"
    
    additional_info_dict = {
        "additional_info1": account_holder_name or licensee_name,
        "additional_info2": "SIKFDR",
        "additional_info3": bank_fdr_code or "SIKFDR",
        "additional_info4": account_holder_name or licensee_name or payer_id,
        "additional_info5": license_type or "NA",
        "additional_info6": district or "NA",
        "additional_info7": "NA",
    }

    api_result = _create_billdesk_order(
        merchant_id=merchant_id,
        client_id=merchant_id.lower(),
        secret_key=encryption_key,
        tx_id=transaction_id,
        amount_str=amount_str,
        return_url=return_url,
        additional_info_dict=additional_info_dict,
        request=request,
        device_data=device_data
    )

    if not api_result.get("success"):
        return Response({"detail": "Failed to initiate transaction with gateway.", "error": api_result.get("error")}, status=status.HTTP_502_BAD_GATEWAY)

    bd_order_id = api_result["bdorderid"]
    auth_token = api_result["authorization"]
    request_msg = api_result["request_string"]

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
            "request_additionalinfo1": account_holder_name or licensee_name,
            "request_additionalinfo2": "SIKFDR",
            "request_additionalinfo3": bank_fdr_code or "SIKFDR",
            "request_additionalinfo4": account_holder_name or licensee_name or payer_id,
            "request_additionalinfo5": license_type or "NA",
            "request_additionalinfo6": district or "NA",
            "request_additionalinfo7": "NA",
            "request_return_url": return_url,
            "request_string": request_msg,
            "payment_status": "P",
            "opr_date": timezone.now(),
            "user_id": str(getattr(request.user, "username", "") or "").strip()[:50],
        },
    )

    try:
        record_wallet_transaction(
            transaction_id=transaction_id,
            licensee_id=payer_id,
            licensee_name=licensee_name,
            wallet_type="security_deposit",
            head_of_account=SECURITY_DEPOSIT_HOA_SENTINEL,
            amount=amount,
            entry_type="CR",
            transaction_type="recharge",
            user_id=str(getattr(request.user, "username", "") or "").strip(),
            source_module="wallet_recharge",
            payment_status="pending",
            remarks="BillDesk payment initiated",
        )
    except Exception as exc:
        logger.warning("Failed to record pending security deposit transaction for txn_id=%s: %s", transaction_id, exc)

    return Response(
        {
            "bd_order_id": bd_order_id,
            "auth_token": auth_token,
            "merchant_id": merchant_id,
            "transaction_id": transaction_id,
            "request_msg": request_msg
        }
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def billdesk_initiate_new_license_application_fee(request):
    # New license application fee payment via BillDesk.
    data = request.data or {}
    device_data = data.get("device_data", {})
    application_id = str(data.get("application_id") or data.get("payer_id") or "").strip()[:50]
    if not application_id:
        return Response({"detail": "application_id is required."}, status=status.HTTP_400_BAD_REQUEST)

    transaction_id = str(data.get("transaction_id") or "").strip() or _generate_transaction_id("NLIAPP")
    raw_amount = data.get("amount")
    payment_module_code = str(data.get("payment_module_code") or "").strip() or DEFAULT_NEW_LICENSE_APPLICATION_MODULE_CODE
    head_of_account = str(data.get("head_of_account") or LICENSE_FEE_HOA).strip() or LICENSE_FEE_HOA

    try:
        payment_module_code = _validate_payment_module_code(payment_module_code)
    except Exception as exc:
        logger.warning(
            "Invalid payment_module_code=%s for new license application fee; proceeding with raw value. err=%s",
            payment_module_code,
            exc,
        )

    try:
        module_fee = _get_module_license_fee(payment_module_code)
        if module_fee is None:
            return Response(
                {
                    "detail": f"license_fee is not configured for payment_module_code={payment_module_code}.",
                    "payment_module_code": payment_module_code,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if raw_amount not in (None, ""):
            client_amount = _normalize_amount(raw_amount)
            if client_amount != module_fee:
                return Response(
                    {
                        "detail": "Invalid amount. Please refresh and try again.",
                        "expected_amount": float(module_fee),
                        "received_amount": float(client_amount),
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

        amount = module_fee
    except Exception as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    pending_tx = _recent_pending_for_payer(application_id)
    if pending_tx:
        existing_txn_id = str(getattr(pending_tx, "utr", "") or getattr(pending_tx, "transaction_id_no_hoa", "") or "").strip()
        if existing_txn_id and existing_txn_id == transaction_id and str(getattr(pending_tx, "request_string", "") or "").strip():
            if getattr(settings, "BILLDESK_USE_MOCK", False):
                billdesk_url = request.build_absolute_uri(reverse("payment_gateway:billdesk-mock-process"))
            else:
                billdesk_url = getattr(settings, "BILLDESK_GATEWAY_URL", "") or ""
            return Response(
                {
                    "billdesk_url": billdesk_url,
                    "request_msg": str(pending_tx.request_string).strip(),
                    "transaction_id": existing_txn_id,
                    "application_id": application_id,
                    "already_pending": True,
                }
            )

        lock_until = (pending_tx.transaction_date or timezone.now()) + timedelta(minutes=PENDING_RETRY_LOCK_MINUTES)
        remaining = int(max(0, (lock_until - timezone.now()).total_seconds()))
        if remaining > 0:
            return _build_pending_retry_response(pending_tx, remaining)

    gateway = (
        PaymentGatewayParameters.objects.filter(is_active=True, payment_gateway_name__iexact="Billdesk")
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
    encryption_key = str(getattr(settings, "BILLDESK_ENCRYPTION_KEY", "") or getattr(gateway, "encryption_key", "") or "").strip()
    if not merchant_id or not security_id or not encryption_key:
        return Response(
            {"detail": "Billdesk gateway config is missing merchantid/securityid/encryption_key."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
    amount_str = f"{amount:.2f}"
    
    additional_info_dict = {
        "additional_info1": head_of_account,
        "additional_info2": "SIKPAY",
        "additional_info3": "SIKPAY",
        "additional_info4": "NA",
        "additional_info5": "NA",
        "additional_info6": "NA",
        "additional_info7": "NA",
    }

    api_result = _create_billdesk_order(
        merchant_id=merchant_id,
        client_id=merchant_id.lower(),
        secret_key=encryption_key,
        tx_id=transaction_id,
        amount_str=amount_str,
        return_url=return_url,
        additional_info_dict=additional_info_dict,
        request=request,
        device_data=device_data
    )

    if not api_result.get("success"):
        return Response({"detail": "Failed to initiate transaction with gateway.", "error": api_result.get("error")}, status=status.HTTP_502_BAD_GATEWAY)

    bd_order_id = api_result["bdorderid"]
    auth_token = api_result["authorization"]
    request_msg = api_result["request_string"]

    PaymentSendHOA.objects.update_or_create(
        transaction_id_no=transaction_id,
        head_of_account=head_of_account,
        defaults={
            "licensee_id": application_id or None,
            "amount": amount,
            "payment_module_code": payment_module_code,
            "requisition_no": (application_id or "NA")[:50],
            "opr_date": timezone.now(),
        },
    )

    PaymentBilldeskTransaction.objects.update_or_create(
        utr=transaction_id,
        defaults={
            "transaction_date": timezone.now(),
            "transaction_id_no_hoa": transaction_id,
            "payer_id": application_id,
            "payment_module_code": payment_module_code,
            "transaction_amount": amount,
            "request_merchantid": merchant_id,
            "request_currencytype": "INR",
            "request_typefield1": "R",
            "request_securityid": security_id,
            "request_typefield2": "F",
            "request_additionalinfo1": head_of_account,
            "request_additionalinfo2": "SIKPAY",
            "request_additionalinfo3": "SIKPAY",
            "request_additionalinfo4": "NA",
            "request_additionalinfo5": "NA",
            "request_additionalinfo6": "NA",
            "request_additionalinfo7": "NA",
            "request_return_url": return_url,
            "request_string": request_msg,
            "payment_status": "P",
            "opr_date": timezone.now(),
            "user_id": str(getattr(request.user, "username", "") or "").strip()[:50],
        },
    )

    return Response(
        {
            "bd_order_id": bd_order_id,
            "auth_token": auth_token,
            "merchant_id": merchant_id,
            "transaction_id": transaction_id,
            "application_id": application_id,
            "request_msg": request_msg
        }
    )


def _process_billdesk_transaction(transaction_response: str) -> bool:
    # 1. Decrypt and verify the incoming SYM-JOSE response
    try:
        resp_data = decrypt_and_verify_billdesk_response(transaction_response)
        checksum_ok = True
    except Exception as e:
        logger.critical(f"SECURITY ALERT: BillDesk JWS/JWE Verification Failed: {e}")
        try:
            # Fallback decode for logging/auditing if possible
            resp_data = _decode_jws_payload(transaction_response)
        except Exception:
            resp_data = {}
        checksum_ok = False

    txn_ref = resp_data.get("orderid", "")
    bank_ref = resp_data.get("bank_ref_no", "")
    resp_amount = resp_data.get("amount", "")
    auth_status = resp_data.get("auth_status", "")
    error_status = resp_data.get("transaction_error_code", "")
    error_desc = resp_data.get("transaction_error_desc", "")
    
    resp_merchantid = resp_data.get("mercid", "")
    resp_txntype = resp_data.get("payment_method_type", "")
    resp_itemcode = resp_data.get("itemcode", "")

    add_info = resp_data.get("additional_info", {})
    resp_additional = [
        add_info.get("additional_info1", ""),
        add_info.get("additional_info2", ""),
        add_info.get("additional_info3", ""),
        add_info.get("additional_info4", ""),
        add_info.get("additional_info5", ""),
        add_info.get("additional_info6", ""),
        add_info.get("additional_info7", "")
    ]

    tx = PaymentBilldeskTransaction.objects.filter(utr=txn_ref).first()
    if tx is None and txn_ref:
        tx = PaymentBilldeskTransaction.objects.filter(transaction_id_no_hoa=txn_ref).first()

    status_code = "S" if (auth_status == "0300" and checksum_ok) else "F"

    if tx:
        try:
            parsed_amount = Decimal(str(resp_amount)).quantize(Decimal("0.01")) if resp_amount else None
        except Exception:
            parsed_amount = None

        # Check if transaction is already marked as success BEFORE processing
        if getattr(tx, "payment_status", "") == "S":
            return True
        
        # Save the raw response string to the DB for auditing
        tx.response_string = transaction_response 
        tx.response_merchantid = resp_merchantid or None
        tx.response_txnreferenceno = txn_ref or None
        tx.response_bankreferenceno = bank_ref or None
        tx.response_txnamount = parsed_amount
        tx.response_txntype = resp_txntype or None
        tx.response_itemcode = resp_itemcode or None
        tx.response_authstatus = auth_status or None
        tx.response_additionalinfo1 = resp_additional[0] or None
        tx.response_additionalinfo2 = resp_additional[1] or None
        tx.response_additionalinfo3 = resp_additional[2] or None
        tx.response_additionalinfo4 = resp_additional[3] or None
        tx.response_additionalinfo5 = resp_additional[4] or None
        tx.response_additionalinfo6 = resp_additional[5] or None
        tx.response_additionalinfo7 = resp_additional[6] or None
        tx.response_errorstatus = error_status or None
        tx.response_errordescription = error_desc or None
        tx.response_initial_authstatus = auth_status or None
        tx.response_initial_datetime = timezone.now()
        tx.payment_status = status_code
        tx.opr_date = timezone.now()
        tx.save()

        module_code = str(getattr(tx, "payment_module_code", "") or "").strip()

        if module_code == DEFAULT_NEW_LICENSE_APPLICATION_MODULE_CODE:
            if status_code == "S":
                try:                 
                    application_id = str(getattr(tx, "payer_id", "") or "").strip()
                    app = (
                        NewLicenseApplication.objects.select_related("workflow", "current_stage", "applicant")
                        .filter(application_id__iexact=application_id)
                        .first()
                    )
                    if not app:
                        raise ValueError(f"NewLicenseApplication not found for application_id={application_id}")

                    # FIXED: Restored update_fields so draft validation doesn't crash the save
                    try:
                        if not getattr(app, "is_application_fee_paid", False):
                            app.is_application_fee_paid = True
                            app.save(update_fields=["is_application_fee_paid"]) 
                    except Exception as e:
                        logger.error(f"Error updating application fee status: {e}", exc_info=True)

                    try:
                        stage = getattr(app, "current_stage", None)
                        stage_name = str(getattr(stage, "name", "") or "").strip().lower()
                        is_rejected_or_final = bool(
                            (stage_name and "reject" in stage_name)
                            or bool(getattr(stage, "is_final", False))
                        )
                        if is_rejected_or_final and getattr(app, "workflow", None):
                            initial = app.workflow.stages.filter(is_initial=True).order_by("id").first()
                            if initial and getattr(app, "current_stage_id", None) != getattr(initial, "id", None):
                                app.current_stage = initial
                                app.save(update_fields=["current_stage"])
                                
                        # Auto-submit
                        if getattr(getattr(app, "current_stage", None), "is_initial", False):
                            username = str(getattr(tx, "user_id", "") or "").strip()
                            user = CustomUser.objects.filter(username__iexact=username).first() if username else getattr(app, "applicant", None)
                            
                            WorkflowService.submit_application(
                                application=app,
                                user=user,
                                remarks="Application fee paid via BillDesk (auto-submitted)",
                            )
                    except Exception as e:
                        logger.error(f"Error auto-submitting workflow for {application_id}: {e}", exc_info=True)
                    
                    
                    sbm_submitted = False
                    sbm_application_id = ""
                    sbm_submit_error = ""
                    try:
                        if getattr(app, "mode_of_operation", None) in {"Salesman", "Barman"}:
                            from models.transactional.salesman_barman.models import SalesmanBarmanModel
                            from auth.workflow.constants import WORKFLOW_IDS
                            from auth.workflow.models import WorkflowStage, Workflow
                            from django.db import transaction as db_transaction

                            wf = Workflow.objects.filter(id=WORKFLOW_IDS.get("SALESMAN_BARMAN")).first()
                            if not wf:
                                raise ValueError(f"SALESMAN_BARMAN workflow (id={WORKFLOW_IDS.get('SALESMAN_BARMAN')}) not found in DB.")

                            init = WorkflowStage.objects.filter(workflow=wf, is_initial=True).order_by("id").first()
                            if not init:
                                raise ValueError("No initial stage found for SALESMAN_BARMAN workflow.")

                            sb = (
                                SalesmanBarmanModel.objects.select_related("workflow", "current_stage", "applicant")
                                .filter(new_license_application=app)
                                .first()
                            )

                            if not sb:
                                sb = SalesmanBarmanModel(
                                    workflow=wf,
                                    current_stage=init,
                                    new_license_application=app,
                                    excise_district=getattr(app, "site_district", None),
                                    license_category=getattr(app, "license_category", None),
                                    license=None,
                                    applicant=user,
                                    role=getattr(app, "mode_of_operation", None),
                                )
                            else:
                                if not getattr(sb, "workflow_id", None):
                                    sb.workflow = wf
                                if not getattr(sb, "current_stage_id", None):
                                    sb.current_stage = init
                                if user and not getattr(sb, "applicant_id", None):
                                    sb.applicant = user
                                if getattr(app, "site_district_id", None):
                                    sb.excise_district = app.site_district
                                if getattr(app, "license_category_id", None):
                                    sb.license_category = app.license_category
                                if getattr(app, "mode_of_operation", None) in {"Salesman", "Barman"}:
                                    sb.role = app.mode_of_operation
                            with db_transaction.atomic():
                                sb.save()

                            sbm_application_id = str(getattr(sb, "application_id", "") or "").strip()

                            sb.refresh_from_db()
                            if getattr(getattr(sb, "current_stage", None), "is_initial", False):
                                try:
                                    WorkflowService.submit_application(
                                        application=sb,
                                        user=user,
                                        remarks="Auto-submitted with New License Application",
                                    )
                                    sbm_submitted = True
                                except Exception as _submit_exc:
                                    logger.exception(
                                        "SB WorkflowService.submit_application failed for sb=%s NLI=%s: %s",
                                        sbm_application_id,
                                        getattr(app, "application_id", "?"),
                                        _submit_exc,
                                    )
                                    sbm_submit_error = f"sbm_workflow_submit_failed: {_submit_exc}"

                    except Exception as _sbm_exc:
                        logger.exception(
                            "SB auto-submit failed for NLI application_id=%s: %s",
                            getattr(app, "application_id", "?"),
                            _sbm_exc,
                        )
                        sbm_submit_error = "sbm_auto_submit_failed"
                    logger.info(
                        f"SB auto-submit complete. Submitted: {sbm_submitted}, "
                        f"ID: {sbm_application_id}, Error: {sbm_submit_error}"
                    )

                except Exception as exc:
                    logger.exception("Failed to auto-submit new license application for txn_ref=%s: %s", txn_ref, exc)
            elif status_code == "F":
                try:
                    application_id = str(getattr(tx, "payer_id", "") or "").strip()
                    app = (
                        NewLicenseApplication.objects.only("application_id", "is_application_fee_paid")
                        .filter(application_id__iexact=application_id)
                        .first()
                    )
                    if app and getattr(app, "is_application_fee_paid", False):
                        app.is_application_fee_paid = False
                        app.save(update_fields=["is_application_fee_paid"])
                except Exception as exc:
                    logger.exception(
                        "Failed to preserve unpaid new license application state for txn_ref=%s: %s",
                        txn_ref,
                        exc,
                    )
        elif module_code == "010":
            if status_code == "S":
                try:
                    from models.transactional.company_collaboration.models import CompanyCollaboration
                    from auth.workflow.models import WorkflowStage
                    from auth.workflow.services import WorkflowService

                    application_id = str(getattr(tx, "payer_id", "") or "").strip()
                    app = CompanyCollaboration.objects.select_related("workflow", "current_stage").filter(
                        application_id__iexact=application_id
                    ).first()

                    if not app:
                        raise ValueError(f"CompanyCollaboration not found for application_id={application_id}")

                    with transaction.atomic():
                        app.is_license_fee_paid = True
                        app.is_security_fee_paid = True
                        target_stage = WorkflowStage.objects.filter(
                            workflow=app.workflow,
                            name__iexact="final_commissioner_review"
                        ).first()

                        if target_stage:
                            app.current_stage = target_stage
                        app.save()

                        username = str(getattr(tx, "user_id", "") or "").strip()
                        user = None
                        if username:
                            user = CustomUser.objects.filter(username__iexact=username).first()
                        if not user:
                            user = getattr(app, "applicant", None)

                        WorkflowService.record_transaction(
                            application=app,
                            user=user,
                            action="PAY",
                            remarks="Payment of Company Collaboration fee completed via BillDesk.",
                        )
                except Exception as exc:
                    logger.exception("Failed to update Company Collaboration stage for txn_ref=%s: %s", txn_ref, exc)
        else:
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

                        if credit_wallet_type == "security_deposit":
                            try:
                                from django.db.models import Q
                                from models.masters.license.models import License
                                from models.transactional.company_collaboration.models import CompanyCollaboration
                                from models.transactional.new_license_application.models import NewLicenseApplication
                                from models.transactional.new_license_application.payment_status import sync_new_license_payment_status
                                from models.transactional.wallet.views import _wallet_license_candidates

                                username = str(getattr(tx, "user_id", "") or "").strip()
                                user = None
                                if username:
                                    user = CustomUser.objects.filter(username__iexact=username).first()
                                if not user:
                                    user = CustomUser.objects.filter(username__iexact=credit_licensee_id).first()

                                candidates = _wallet_license_candidates(credit_licensee_id)
                                lic = License.objects.filter(license_id__in=candidates).order_by("-issue_date", "-license_id").first()
                                application = None
                                if lic and lic.source_type == "new_license_application":
                                    application = NewLicenseApplication.objects.filter(application_id=lic.source_object_id).first()

                                if not application or getattr(application, "is_approved", False) or getattr(application, "is_security_fee_paid", False):
                                    if not user and lic:
                                        user = getattr(lic, "applicant", None)

                                    if user:
                                        pending_app = NewLicenseApplication.objects.filter(
                                            applicant=user,
                                            is_approved=False,
                                            is_security_fee_paid=False
                                        ).filter(
                                            Q(current_stage__name__icontains="payment") |
                                            Q(current_stage__name__icontains="awaiting")
                                        ).first()

                                        if not pending_app:
                                            pending_app = NewLicenseApplication.objects.filter(
                                                applicant=user,
                                                is_approved=False,
                                                is_security_fee_paid=False
                                            ).first()

                                        if pending_app:
                                            application = pending_app

                                if application and not application.is_security_fee_paid:
                                    application.is_security_fee_paid = True
                                    application.save(update_fields=["is_security_fee_paid"])
                                    sync_new_license_payment_status(application)
                            except Exception as auto_pay_error:
                                logger.error("Auto security fee payment in Billdesk callback failed: %s", str(auto_pay_error), exc_info=True)
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

    return {
        "success": True,
        "sbm_submitted": locals().get("sbm_submitted", False),
        "sbm_application_id": locals().get("sbm_application_id", ""),
        "sbm_submit_error": locals().get("sbm_submit_error", "")
    }

@csrf_exempt
def billdesk_webhook(request):
    """
    Dedicated endpoint for BillDesk Server-to-Server Webhooks.
    """
    if request.method != "POST":
        return HttpResponseBadRequest("Invalid method")

    transaction_response = request.POST.get("transaction_response")
    if not transaction_response:
        transaction_response = request.body.decode('utf-8').strip()

    if not transaction_response:
        return HttpResponse("Missing payload", status=200)

    _process_billdesk_transaction(transaction_response)

    return HttpResponse("Webhook Received", status=200)

import urllib.parse

@csrf_exempt
def billdesk_response(request):
    if request.method != "POST":
        return HttpResponseBadRequest("Invalid method")

    transaction_response = request.POST.get("transaction_response")
    if not transaction_response:
        return HttpResponseBadRequest("Missing transaction_response parameter")

    _process_billdesk_transaction(transaction_response)

    try:
        resp_data = _decode_jws_payload(transaction_response)
        txn_ref = resp_data.get("orderid", "")
    except Exception:
        txn_ref = ""

    tx = None
    if txn_ref:
        tx = PaymentBilldeskTransaction.objects.filter(utr=txn_ref).first() or \
             PaymentBilldeskTransaction.objects.filter(transaction_id_no_hoa=txn_ref).first()

    gateway = PaymentGatewayParameters.objects.filter(
        is_active=True, 
        payment_gateway_name__iexact="Billdesk"
    ).order_by("sl_no").first()
    
    base_redirect_url = getattr(gateway, "frontend_success_url", "/") or "/"

    if tx:
        amount_val = str(tx.response_txnamount or tx.transaction_amount or "0")
        wallet_type_val = str(tx.request_additionalinfo3 or "").strip()
        hoa_val = str(tx.request_additionalinfo1 or "").strip()
        status_val = "success" if tx.payment_status == "S" else "failed"
        credit_time = (tx.response_txndate or tx.opr_date or timezone.now()).strftime("%d-%m-%Y %I:%M %p")
        credit_time_iso = (tx.response_txndate or tx.opr_date or timezone.now()).isoformat()

        params = {
            "transaction_id": tx.utr or tx.transaction_id_no_hoa or txn_ref,
            "transactionId": tx.utr or tx.transaction_id_no_hoa or txn_ref,
            "amount": amount_val,
            "wallet_type": wallet_type_val,
            "walletType": wallet_type_val,
            "hoa": hoa_val,
            "head_of_account": hoa_val,
            "status": status_val,
            "payment_status": tx.payment_status,
            "createdAt": credit_time,
            "created_at": credit_time,
            "creditedAt": credit_time,
            "credited_at": credit_time,
            "date": credit_time,
            "txnDate": credit_time_iso,
        }

        url_parts = urllib.parse.urlparse(base_redirect_url)
        query_dict = dict(urllib.parse.parse_qsl(url_parts.query))
        query_dict.update(params)
        new_query = urllib.parse.urlencode(query_dict)
        redirect_url = urllib.parse.urlunparse((
            url_parts.scheme,
            url_parts.netloc,
            url_parts.path,
            url_parts.params,
            new_query,
            url_parts.fragment
        ))
    else:
        redirect_url = base_redirect_url

    dynamic_html = f"""
    <!DOCTYPE html>
    <html>
        <head>
            <title>Processing Payment...</title>
            <style>
                body {{ font-family: Arial, sans-serif; text-align: center; padding-top: 50px; background-color: #f4f7f6; }}
                .container {{ background: white; padding: 30px; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); display: inline-block; }}
                .spinner {{ margin: 20px auto; border: 4px solid #f3f3f3; border-top: 4px solid #3498db; border-radius: 50%; width: 30px; height: 30px; animation: spin 1s linear infinite; }}
                @keyframes spin {{ 0% {{ transform: rotate(0deg); }} 100% {{ transform: rotate(360deg); }} }}
            </style>
        </head>
        <body>
            <div class="container">
                <h2 style="color: #4CAF50;">Payment Processed Successfully!</h2>
                <p>Returning you to the dashboard...</p>
                <div class="spinner"></div>
            </div>

            <script>
                function executeRedirect() {{
                    var targetUrl = "{redirect_url}";
                    
                    try {{
                        // FIXED: Do NOT redirect window.opener. Just close the popup so the WebSDK responseHandler can fire!
                        if (window.opener && !window.opener.closed) {{
                            window.close();
                            return;
                        }}

                        if (window.top && window.top !== window) {{
                            window.top.location.href = targetUrl;
                            return;
                        }}
                    }} catch (error) {{
                        console.warn("Could not access parent/opener window:", error);
                    }}

                    window.close();
                    setTimeout(function() {{
                        if (!window.closed) {{
                            window.location.href = targetUrl;
                        }}
                    }}, 500);
                }}

                // Reduced timeout for a snappy close
                setTimeout(executeRedirect, 500);
            </script>
        </body>
    </html>
    """
    
    return HttpResponse(dynamic_html, content_type="text/html")


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def list_billdesk_transactions(request):
    from django.db.models import Q
    
    # Authorization check: only allow roleId 1 (Site Admin) or roleId 3 (Single Window)
    role_id = getattr(getattr(request.user, 'role', None), 'id', None)
    if role_id not in (1, 3):
        return Response({"detail": "Permission denied. Admin/Single Window only."}, status=status.HTTP_403_FORBIDDEN)

    queryset = PaymentBilldeskTransaction.objects.all()

    # Filters
    query = request.query_params.get("query", "").strip()
    status_filter = request.query_params.get("status", "").strip()
    day = request.query_params.get("day", "").strip()
    month = request.query_params.get("month", "").strip()
    year = request.query_params.get("year", "").strip()
    module = request.query_params.get("module", "").strip()
    
    if status_filter:
        queryset = queryset.filter(payment_status__iexact=status_filter)

    if day.isdigit():
        queryset = queryset.filter(transaction_date__day=int(day))
    if month.isdigit():
        queryset = queryset.filter(transaction_date__month=int(month))
    if year.isdigit():
        queryset = queryset.filter(transaction_date__year=int(year))
    if module:
        if module == '001':
            queryset = queryset.exclude(payment_module_code__in=['002', '999'])
        else:
            queryset = queryset.filter(payment_module_code=module)

    if query:
        # Check if amount query
        amount_query = None
        try:
            amount_query = float(query)
        except ValueError:
            pass

        q_obj = Q(utr__icontains=query) | Q(transaction_id_no_hoa__icontains=query) | Q(payer_id__icontains=query) | Q(user_id__icontains=query)
        if amount_query is not None:
            q_obj |= Q(transaction_amount=amount_query)
        queryset = queryset.filter(q_obj)

    queryset = queryset.order_by('-transaction_date')

    # Pagination parameters
    try:
        page = int(request.query_params.get("page", 1))
        page_size = int(request.query_params.get("page_size", 10))
    except (ValueError, TypeError):
        page = 1
        page_size = 10

    page = max(1, page)
    page_size = max(1, min(page_size, 100))

    total_count = queryset.count()
    offset = (page - 1) * page_size
    items = queryset[offset: offset + page_size]

    # Resolve applicant names helper
    def get_user_display_name(u):
        if not u:
            return "N/A"
        name = f"{getattr(u, 'first_name', '') or ''} {getattr(u, 'last_name', '') or ''}".strip()
        return name or getattr(u, "username", None) or "N/A"

    def resolve_name(reference):
        ref = str(reference or "").strip()
        if not ref:
            return "N/A"
        try:
            # Try NewLicenseApplication
            app = NewLicenseApplication.objects.select_related("applicant").filter(application_id__iexact=ref).first()
            if app:
                return get_user_display_name(app.applicant)

            # Try RenewalApplication
            from models.transactional.license_renewal_application.models import LicenseApplication as RenewalApplication
            renewal = RenewalApplication.objects.select_related("applicant").filter(application_id__iexact=ref).first()
            if renewal:
                return get_user_display_name(renewal.applicant)

            # Try SalesmanBarmanModel
            from models.transactional.salesman_barman.models import SalesmanBarmanModel
            staff = SalesmanBarmanModel.objects.filter(application_id__iexact=ref).first()
            if staff:
                return f"{staff.firstName or ''} {staff.lastName or ''}".strip() or get_user_display_name(staff.applicant)

            # Try License
            from models.masters.license.models import License
            license_obj = License.objects.select_related("applicant").filter(license_id__iexact=ref).first()
            if license_obj:
                return get_user_display_name(license_obj.applicant)

            # Try direct user match
            user_filter = Q(username__iexact=ref)
            if ref.isdigit():
                user_filter |= Q(id=int(ref))
            user = CustomUser.objects.filter(user_filter).first()
            return get_user_display_name(user) if user else "N/A"
        except Exception:
            return "N/A"

    serialized_data = []
    for tx in items:
        # Resolve module code description
        purpose = "Application Fee"
        if tx.payment_module_code == "002":
            purpose = "Renewal Fee"
        elif tx.payment_module_code == "999":
            purpose = "Wallet Recharge"
        else:
            try:
                mod = MasterPaymentModule.objects.filter(module_code=tx.payment_module_code).first()
                if mod and mod.module_desc:
                    purpose = mod.module_desc
                else:
                    # fallback to MasterFixedFee
                    from models.masters.core.models import MasterFixedFee
                    fixed_fee = MasterFixedFee.objects.filter(fee_code=tx.payment_module_code).first()
                    if fixed_fee and fixed_fee.fee_desc:
                        purpose = fixed_fee.fee_desc
            except Exception:
                pass

        # Resolve applicant name
        applicant_name = resolve_name(tx.payer_id)
        if applicant_name == "N/A" and tx.user_id:
            applicant_name = resolve_name(tx.user_id)

        serialized_data.append({
            "utr": tx.utr,
            "transaction_date": tx.transaction_date.isoformat() if tx.transaction_date else None,
            "transaction_id_no_hoa": tx.transaction_id_no_hoa,
            "payer_id": tx.payer_id,
            "payment_module_code": tx.payment_module_code,
            "purpose": purpose,
            "transaction_amount": str(tx.transaction_amount),
            "payment_status": tx.payment_status,
            "user_id": tx.user_id,
            "applicant_name": applicant_name,
            "response_bankreferenceno": tx.response_bankreferenceno,
            "response_txndate": tx.response_txndate.isoformat() if tx.response_txndate else None,
            "response_errordescription": tx.response_errordescription,
            "response_authstatus": tx.response_authstatus,
        })

    return Response({
        'count': total_count,
        'page': page,
        'page_size': page_size,
        'total_pages': (total_count + page_size - 1) // page_size,
        'results': serialized_data,
    })


@api_view(["GET"])
@permission_classes([AllowAny])
def revenue_receipts_chart_data(request):
    from django.db.models import Sum
    from django.utils import timezone
    from datetime import datetime
    
    chart_data = []
    from django.db.models import Max
    max_db_date = PaymentBilldeskTransaction.objects.aggregate(max_date=Max('transaction_date'))['max_date']
    if max_db_date:
        max_year = max(timezone.now().year, max_db_date.year)
    else:
        max_year = timezone.now().year
    
    for year in range(2020, max_year + 1):
        fy_label = f"{year}-{year+1}"
        
        # Create timezone-aware datetime objects to avoid Naive Datetime warnings
        start_dt = datetime(year, 4, 1, 0, 0, 0)
        end_dt = datetime(year + 1, 3, 31, 23, 59, 59)
        start_date = timezone.make_aware(start_dt)
        end_date = timezone.make_aware(end_dt)
        
        db_total = PaymentBilldeskTransaction.objects.filter(
            payment_status='S',
            transaction_date__range=[start_date, end_date]
        ).aggregate(total=Sum('transaction_amount'))['total'] or 0
        
        if db_total > 0:
            chart_data.append({
                "financial_year": fy_label,
                "amount": float(db_total),
                "source": "database"
            })
        
    return Response(chart_data)
