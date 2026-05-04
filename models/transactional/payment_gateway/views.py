import hashlib
import hmac
import html
import logging
from urllib.parse import urlencode
from decimal import Decimal
import secrets
from datetime import timedelta
import json
import base64
import requests
import time
from .billdesk_utils import generate_billdesk_jws, verify_billdesk_jws
from django.conf import settings
from django.db.utils import OperationalError, ProgrammingError
from django.http import HttpResponse, HttpResponseBadRequest
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.urls import reverse
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from auth.workflow.models import WorkflowStage
from models.transactional.new_license_application.models import NewLicenseApplication
from auth.user.models import CustomUser
from auth.workflow.services import WorkflowService
from .models import PaymentBilldeskTransaction, PaymentGatewayParameters, PaymentSendHOA, MasterPaymentModule
from models.transactional.wallet.wallet_service import credit_wallet_balance, record_wallet_transaction

logger = logging.getLogger(__name__)

LICENSE_FEE_HOA = "0039-00-800-45-02"
SECURITY_DEPOSIT_HOA_SENTINEL = "non"
DEFAULT_LICENSE_RENEWAL_MODULE_CODE = "002"
DEFAULT_WALLET_ADVANCE_MODULE_CODE = "999"
DEFAULT_NEW_LICENSE_APPLICATION_MODULE_CODE = "001"
PENDING_RETRY_LOCK_MINUTES = 15


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

    # check sems_master_module if it exists in the DB.
    try:
        if MasterPaymentModule.objects.filter(module_code=code).exists():
            return code
    except (OperationalError, ProgrammingError):
        pass

    raise ValueError(f"Invalid payment_module_code={code}. Not found in master module table.")


def _generate_transaction_id(prefix: str = "TXN") -> str:
    return f"{prefix}{timezone.now().strftime('%Y%m%d%H%M%S')}{secrets.token_hex(4).upper()}"

# Helper function to decode the JWS token payload without verifying the signature.
def _decode_jws_payload(jws_token: str) -> dict:
    """Decodes the Base64URL payload of a JWS token into a Python dictionary."""
    parts = jws_token.split('.')
    if len(parts) != 3:
        return {}
    payload_b64 = parts[1]
    # Add padding back if necessary for standard base64 decoding
    padding = '=' * (4 - len(payload_b64) % 4)
    payload_json = base64.urlsafe_b64decode(payload_b64 + padding).decode('utf-8')
    return json.loads(payload_json)

def _create_billdesk_order(merchant_id, client_id, secret_key, tx_id, amount_str, return_url, additional_info_dict, request, device_data=None):
    """Makes the server-to-server call to BillDesk to create an order."""
    if device_data is None:
        device_data = {}

    # Safely determine the actual client IP (handling proxies/load balancers)
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        client_ip = x_forwarded_for.split(',')[0].strip()
    else:
        client_ip = request.META.get('REMOTE_ADDR', '127.0.0.1')

    print(f"Client IP determined for BillDesk order creation: {client_ip}") # Debug log to verify IP extraction

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
            "user_agent": device_data.get("user_agent") or request.META.get('HTTP_USER_AGENT', 'Mozilla/5.0')[:250],
            "accept_header": device_data.get("accept_header", "text/html"),
            "browser_tz": str(device_data.get("browser_tz", "-330")),
            "browser_color_depth": str(device_data.get("browser_color_depth", "32")),
            "browser_java_enabled": str(device_data.get("browser_java_enabled", "false")).lower(),
            "browser_screen_height": str(device_data.get("browser_screen_height", "1080")),
            "browser_screen_width": str(device_data.get("browser_screen_width", "1920")),
            "browser_language": device_data.get("browser_language", "en-US"),
            "browser_javascript_enabled": str(device_data.get("browser_javascript_enabled", "true")).lower()
        }
    }
    
    jws_token = generate_billdesk_jws(client_id, secret_key, payload)
    
    headers = {
        "Content-Type": "application/jose",
        "Accept": "application/jose",
        "BD-Traceid": tx_id,
        "BD-Timestamp": str(int(time.time() * 1000))
    }
    
    # UAT URL
    api_url = "https://uat1.billdesk.com/u2/payments/ve1_2/orders/create"
    
    response = requests.post(api_url, data=jws_token, headers=headers)
    
    if response.status_code == 200:
        resp_jws = response.text
        resp_data = _decode_jws_payload(resp_jws)
        
        bdorderid = resp_data.get("bdorderid")
        auth_token = None
        
        # Extract the authToken from the redirect link headers[cite: 1]
        for link in resp_data.get("links", []):
            if link.get("rel") == "redirect":
                auth_token = link.get("headers", {}).get("authorization")
                break
                
        return {
            "success": True, 
            "bdorderid": bdorderid, 
            "authorization": auth_token, 
            "request_string": jws_token # Saving this for debugging/DB purposes
        }
    else:
        logger.error(f"BillDesk Create Order Failed: {response.text}")
        return {"success": False, "error": response.text}


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
    device_data = data.get("device_data", {})
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

    # Call the Create Order API
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

    # 3. Extract the SDK variables
    bd_order_id = api_result["bdorderid"]
    auth_token = api_result["authorization"]
    request_msg = api_result["request_string"] # The JWS token sent to BillDesk

    # 4. Save to DB (update your update_or_create call)
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
            # "request_checksum": checksum,
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

    try:
        record_wallet_transaction(
            transaction_id=transaction_id,
            licensee_id=str(data.get("licensee_id") or data.get("licenseeId") or payer_id or "").strip()[:50] or payer_id,
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

   # 5. Return SDK tokens to Frontend
    return Response(
        {
            "bd_order_id": bd_order_id,
            "auth_token": auth_token,
            "merchant_id": merchant_id,
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
    device_data = data.get("device_data", {})

    transaction_id = str(data.get("transaction_id") or "").strip() or _generate_transaction_id("SIKPAY")
    payer_id = str(data.get("payer_id") or data.get("licensee_id") or "").strip()[:50]
    payment_module_code = str(data.get("payment_module_code") or "").strip() or DEFAULT_LICENSE_RENEWAL_MODULE_CODE
    raw_amount = data.get("amount")

    if not payer_id:
        return Response({"detail": "payer_id (licensee id) is required."}, status=status.HTTP_400_BAD_REQUEST)

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
    
    additional_info_dict = {
        "additional_info1": LICENSE_FEE_HOA,
        "additional_info2": "SIKPAY",
        "additional_info3": "SIKPAY",
        "additional_info4": "NA",
        "additional_info5": "NA",
        "additional_info6": "NA",
        "additional_info7": "NA",
    }

    # Call the Create Order API
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
        return Response({"detail": "licensee_id is required."}, status=status.HTTP_400_BAD_REQUEST)

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
    
    additional_info_dict = {
        "additional_info1": account_holder_name or licensee_name,
        "additional_info2": "SIKFDR",
        "additional_info3": bank_fdr_code or "SIKFDR",
        "additional_info4": account_holder_name or licensee_name or payer_id,
        "additional_info5": license_type or "NA",
        "additional_info6": district or "NA",
        "additional_info7": "NA",
    }

    # Call the Create Order API
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
    """
    New license application fee payment via BillDesk.

    - payment_module_code: 001 (New Licensee Application) from master module table
    - payer_id: application_id (NLI/...)
    - AdditionalInfo2/3: SIKPAY (legacy mapping expected by BillDesk integrations)
    """
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
        amount = _normalize_amount(raw_amount or Decimal("500.00"))
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
    
    additional_info_dict = {
        "additional_info1": head_of_account,
        "additional_info2": "SIKPAY",
        "additional_info3": "SIKPAY",
        "additional_info4": "NA",
        "additional_info5": "NA",
        "additional_info6": "NA",
        "additional_info7": "NA",
    }

    # Call the Create Order API
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


@csrf_exempt
def billdesk_response(request):
    if request.method != "POST":
        return HttpResponseBadRequest("Invalid method")

    auto_submitted = False
    auto_submit_error = ""

    # 1. Fetch the new encrypted response parameter[cite: 1]
    transaction_response = request.POST.get("transaction_response")
    if not transaction_response:
        return HttpResponseBadRequest("Missing transaction_response parameter")

    # 2. Decode the JWS payload[cite: 1]
    try:
        resp_data = _decode_jws_payload(transaction_response)
    except Exception as e:
        logger.error(f"Failed to decode JWS: {e}")
        return HttpResponseBadRequest("Invalid response format")

    # 3. Extract parameters directly from the JSON dictionary[cite: 1]
    txn_ref = resp_data.get("orderid", "")
    bank_ref = resp_data.get("bank_ref_no", "")
    resp_amount = resp_data.get("amount", "")
    auth_status = resp_data.get("auth_status", "")
    error_status = resp_data.get("transaction_error_code", "")
    error_desc = resp_data.get("transaction_error_desc", "")
    
    resp_merchantid = resp_data.get("mercid", "")
    resp_txntype = resp_data.get("payment_method_type", "")
    resp_itemcode = resp_data.get("itemcode", "")

    # Extract additional info dictionary[cite: 1]
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

    # Fetch the Gateway config to get the encryption (secret) key
    gateway = PaymentGatewayParameters.objects.filter(
        is_active="Y", 
        payment_gateway_name__iexact="Billdesk"
    ).order_by("sl_no").first()
    
    encryption_key = str(getattr(gateway, "encryption_key", "") or "").strip()

    tx = None
    if txn_ref:
        tx = PaymentBilldeskTransaction.objects.filter(utr=txn_ref).first()
        if tx is None:
            tx = PaymentBilldeskTransaction.objects.filter(transaction_id_no_hoa=txn_ref).first()

    # VERIFY THE SIGNATURE
    checksum_ok = False
    if encryption_key:
        checksum_ok = verify_billdesk_jws(transaction_response, encryption_key)
    else:
        logger.error("Encryption key missing from Gateway Parameters.")

    if not checksum_ok:
        logger.critical(f"SECURITY ALERT: Invalid JWS Signature detected for order {txn_ref}!")
        # Force a failure status if the signature is spoofed
        status_code = "F" 
    else:
        # Proceed with normal status checking
        status_code = "S" if auth_status == "0300" else "F"

    if tx:
        try:
            parsed_amount = Decimal(str(resp_amount)).quantize(Decimal("0.01")) if resp_amount else None
        except Exception:
            parsed_amount = None

        status_code = "S" if auth_status == "0300" and checksum_ok else "F"
        
        # Save the raw JWS string to the DB for auditing
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
            # New license application fee: auto-submit application on success.
            if status_code == "S":
                try:                 
                    # WorkflowStage import is intentionally inside try-block for environments where workflow tables differ.
                    application_id = str(getattr(tx, "payer_id", "") or "").strip()
                    app = (
                        NewLicenseApplication.objects.select_related("workflow", "current_stage", "applicant")
                        .filter(application_id__iexact=application_id)
                        .first()
                    )
                    if not app:
                        raise ValueError(f"NewLicenseApplication not found for application_id={application_id}")

                    # Persist application-fee payment status on the application row.
                    try:
                        if not getattr(app, "is_application_fee_paid", False):
                            app.is_application_fee_paid = True
                            app.save(update_fields=["is_application_fee_paid"])
                    except Exception:
                        pass

                    # If a previous attempt incorrectly pushed the application into a rejected/final stage,
                    # restore it back to the workflow initial stage so it can be submitted.
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
                    except Exception:
                        pass

                    username = str(getattr(tx, "user_id", "") or "").strip()
                    user = None
                    if username:
                        user = CustomUser.objects.filter(username__iexact=username).first()
                    if not user:
                        user = getattr(app, "applicant", None)

                    if getattr(getattr(app, "current_stage", None), "is_initial", False):
                        WorkflowService.submit_application(
                            application=app,
                            user=user,
                            remarks="Application fee paid via BillDesk (auto-submitted)",
                        )
                    auto_submitted = True
                except Exception as exc:
                    auto_submit_error = str(exc)
                    logger.exception("Failed to auto-submit new license application for txn_ref=%s: %s", txn_ref, exc)
            elif status_code == "F":
                # Do not mark the application as rejected on application-fee payment failure.
                # The licensee should be able to retry "Pay Now" later while the application remains unsubmitted.
                try:
                    from models.transactional.new_license_application.models import NewLicenseApplication

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
        else:
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

    if tx and str(getattr(tx, "payment_module_code", "") or "").strip() == DEFAULT_NEW_LICENSE_APPLICATION_MODULE_CODE:
        configured = str(getattr(settings, "PAYMENT_GATEWAY_FRONTEND_NEW_LICENSE_RECEIPT_URL", "") or "").strip()
        if configured:
            frontend_success = configured
    if not frontend_success:
        return HttpResponseBadRequest(
            "Frontend success URL not configured (set Payment_Gateway_Parameters.frontend_success_url or PAYMENT_GATEWAY_FRONTEND_SUCCESS_URL)."
        )

    if tx:
        module_code = str(getattr(tx, "payment_module_code", "") or "").strip()
        if module_code == DEFAULT_NEW_LICENSE_APPLICATION_MODULE_CODE:
            wallet_type = "application_fee"
            hoa = str(tx.request_additionalinfo1 or "").strip()
        else:
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
    # query = urlencode(
    #     {
    #         "transactionId": txn_ref,
    #         "paymentModuleCode": str(getattr(tx, "payment_module_code", "") or "").strip() if tx else "",
    #         "payerId": str(getattr(tx, "payer_id", "") or "").strip() if tx else "",
    #         "applicationId": str(getattr(tx, "payer_id", "") or "").strip() if tx else "",
    #         "walletType": wallet_type,
    #         "hoa": hoa,
    #         "amount": amt,
    #         "status": ui_status,
    #         "reason": ui_reason,
    #         "createdAt": created_at,
    #         "additionalInfo2": str(getattr(tx, "request_additionalinfo2", "") or "").strip() if tx else "",
    #         "additionalInfo3": str(getattr(tx, "request_additionalinfo3", "") or "").strip() if tx else "",
    #         "autoSubmitted": "1" if auto_submitted else "0",
    #         "autoSubmitError": auto_submit_error[:200] if auto_submit_error else "",
    #     }
    # )
    html_content = """
    <!DOCTYPE html>
    <html>
        <head><title>Processing Payment...</title></head>
        <body onload="window.close();">
            <p>Payment processed successfully. You may safely close this window.</p>
        </body>
    </html>
    """
    return HttpResponse(html_content, content_type="text/html")


# @csrf_exempt
# def billdesk_mock_process(request):
#     """
#     Localhost testing helper.

#     The Angular app auto-POSTs `msg=<request_msg>` to the BillDesk gateway URL.
#     When BILLDESK_USE_MOCK=1, our initiate endpoint returns this mock URL instead.

#     This endpoint simulates BillDesk's ProcessPayment by generating a response `msg`
#     (with checksum) and auto-POSTing it to our `/billdesk/response/` handler.
#     """
#     if request.method != "POST":
#         return HttpResponseBadRequest("Invalid method")

#     incoming = str(request.POST.get("msg") or request.POST.get("MSG") or "").strip()
#     if not incoming:
#         return HttpResponseBadRequest("Missing msg")

#     if getattr(settings, "BILLDESK_MOCK_SIMULATE_PENDING", False):
#         return HttpResponse(
#             """
#             <html>
#               <head><title>BillDesk Mock - Pending</title></head>
#               <body style="font-family: Arial, sans-serif; padding: 24px;">
#                 <h3>BillDesk Mock</h3>
#                 <p><strong>Simulating a stuck/pending payment:</strong> no callback will be sent to the server.</p>
#                 <p>You can close this page and check wallet history status as <code>Pending</code>.</p>
#               </body>
#             </html>
#             """
#         )

#     req_parts = incoming.split("|")
#     if len(req_parts) < 5:
#         return HttpResponseBadRequest("Invalid request msg format")

#     merchant_id = req_parts[0].strip()
#     txn_ref = req_parts[1].strip()
#     amount = req_parts[3].strip()

#     gateway = (
#         PaymentGatewayParameters.objects.filter(is_active="Y", payment_gateway_name__iexact="Billdesk")
#         .order_by("sl_no")
#         .first()
#     )
#     encryption_key = str(getattr(gateway, "encryption_key", "") or "").strip()
#     if not encryption_key:
#         return HttpResponseBadRequest("Missing encryption key")

#     auth_status = str(getattr(settings, "BILLDESK_MOCK_AUTH_STATUS", "0300") or "0300").strip()
#     error_status = "NA" if auth_status == "0300" else "ERR"
#     error_desc = "NA" if auth_status == "0300" else "MOCK_FAILED"

#     # Build a realistic BillDesk response string (checksum appended at end).
#     # MerchantID|CustomerID|TxnReferenceNo|BankReferenceNo|TxnAmount|BankID|BankMerchantID|TxnType|CurrencyName|ItemCode|
#     # SecurityType|SecurityID|SecurityPassword|TxnDate|AuthStatus|SettlementType|AdditionalInfo1..7|ErrorStatus|ErrorDescription|Checksum
#     customer_id = "NA"
#     bank_ref = f"MOCK{timezone.now().strftime('%Y%m%d%H%M%S')}"
#     bank_id = "NA"
#     bank_merchant_id = "NA"
#     txn_type = "NA"
#     currency = "INR"
#     item_code = "NA"
#     security_type = "NA"
#     security_id = str(getattr(gateway, "securityid", "") or "").strip() or "NA"
#     security_password = "NA"
#     txn_date = timezone.now().strftime("%Y-%m-%d %H:%M:%S")
#     settlement_type = "NA"

#     # Try to echo back additional info from our stored request (if present).
#     tx = PaymentBilldeskTransaction.objects.filter(utr=txn_ref).first()
#     add = [
#         str(getattr(tx, "request_additionalinfo1", "") or "NA"),
#         str(getattr(tx, "request_additionalinfo2", "") or "NA"),
#         str(getattr(tx, "request_additionalinfo3", "") or "NA"),
#         str(getattr(tx, "request_additionalinfo4", "") or "NA"),
#         str(getattr(tx, "request_additionalinfo5", "") or "NA"),
#         str(getattr(tx, "request_additionalinfo6", "") or "NA"),
#         str(getattr(tx, "request_additionalinfo7", "") or "NA"),
#     ]

#     resp_without_checksum = (
#         f"{merchant_id}|{customer_id}|{txn_ref}|{bank_ref}|{amount}|{bank_id}|{bank_merchant_id}|{txn_type}|"
#         f"{currency}|{item_code}|{security_type}|{security_id}|{security_password}|{txn_date}|{auth_status}|"
#         f"{settlement_type}|{add[0]}|{add[1]}|{add[2]}|{add[3]}|{add[4]}|{add[5]}|{add[6]}|{error_status}|{error_desc}"
#     )
#     resp_checksum = _billdesk_hmac_sha256(resp_without_checksum, encryption_key)
#     response_msg = f"{resp_without_checksum}|{resp_checksum}"

#     fail_auth_status = "0399"
#     fail_error_status = "ERR"
#     fail_error_desc = "MOCK_FAILED"
#     resp_without_checksum_fail = (
#         f"{merchant_id}|{customer_id}|{txn_ref}|{bank_ref}|{amount}|{bank_id}|{bank_merchant_id}|{txn_type}|"
#         f"{currency}|{item_code}|{security_type}|{security_id}|{security_password}|{txn_date}|{fail_auth_status}|"
#         f"{settlement_type}|{add[0]}|{add[1]}|{add[2]}|{add[3]}|{add[4]}|{add[5]}|{add[6]}|{fail_error_status}|{fail_error_desc}"
#     )
#     resp_checksum_fail = _billdesk_hmac_sha256(resp_without_checksum_fail, encryption_key)
#     response_msg_fail = f"{resp_without_checksum_fail}|{resp_checksum_fail}"

#     callback_url = reverse("payment_gateway:billdesk-response")

#     escaped_msg = html.escape(response_msg, quote=True)
#     escaped_msg_fail = html.escape(response_msg_fail, quote=True)
#     escaped_txn = html.escape(txn_ref, quote=True)
#     escaped_amount = html.escape(amount, quote=True)
#     escaped_status = html.escape(auth_status, quote=True)

#     # Show a simple BillDesk-like page so testers can actually "see" the payment step.
#     page = f"""
# <!doctype html>
# <html>
#   <head>
#     <meta charset="utf-8">
#     <title>BillDesk Mock Payment</title>
#     <meta name="viewport" content="width=device-width, initial-scale=1">
#     <style>
#       body {{ font-family: Arial, sans-serif; margin: 24px; background: #f6f7fb; }}
#       .card {{ max-width: 720px; margin: 0 auto; background: #fff; border: 1px solid #e6e8f0; border-radius: 10px; padding: 18px 18px 14px; }}
#       .hdr {{ font-size: 18px; font-weight: 700; margin-bottom: 8px; }}
#       .sub {{ color: #556; margin-bottom: 18px; }}
#       .row {{ display: flex; gap: 12px; margin: 8px 0; }}
#       .k {{ width: 220px; color: #334; font-weight: 600; }}
#       .v {{ flex: 1; color: #111; word-break: break-all; }}
#       .btns {{ display: flex; gap: 10px; margin-top: 18px; }}
#       button {{ border: 0; border-radius: 8px; padding: 10px 14px; cursor: pointer; font-weight: 700; }}
#       .pay {{ background: #16a34a; color: #fff; }}
#       .fail {{ background: #dc2626; color: #fff; }}
#       .note {{ margin-top: 14px; color: #667; font-size: 12px; }}
#     </style>
#   </head>
#   <body>
#     <div class="card">
#       <div class="hdr">BillDesk Mock Payment Page</div>
#       <div class="sub">This page is shown only when <code>BILLDESK_USE_MOCK=1</code> for localhost testing.</div>

#       <div class="row"><div class="k">Transaction</div><div class="v">{escaped_txn}</div></div>
#       <div class="row"><div class="k">Amount</div><div class="v">{escaped_amount}</div></div>
#       <div class="row"><div class="k">AuthStatus (mock)</div><div class="v">{escaped_status}</div></div>

#       <div class="btns">
#         <form method="POST" action="{callback_url}">
#           <input type="hidden" name="msg" value="{escaped_msg}">
#           <button type="submit" class="pay">Pay (Post Response)</button>
#         </form>
#         <form method="POST" action="{callback_url}">
#           <input type="hidden" name="msg" value="{escaped_msg_fail}">
#           <button type="submit" class="fail">Fail</button>
#         </form>
#       </div>

#       <div class="note">Tip: set <code>BILLDESK_MOCK_AUTH_STATUS</code> to control the default success status (0300).</div>
#     </div>
#   </body>
# </html>
# """.strip()
#     return HttpResponse(page, content_type="text/html")
