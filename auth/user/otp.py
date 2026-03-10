import random
from datetime import timedelta
from django.utils import timezone
from django.db import transaction
from django.conf import settings
from auth.user.models import OTP
from django.core.cache import cache
import logging
import requests
import re
from urllib.parse import quote, urlencode, unquote

logger = logging.getLogger(__name__)


def _mask_phone(phone_number: str) -> str:
    value = str(phone_number or "")
    if len(value) < 4:
        return "****"
    return ("*" * max(0, len(value) - 4)) + value[-4:]


def _looks_like_gateway_failure(response_text: str) -> bool:
    """
    Basic failure detection for plain-text SMS gateway responses.
    """
    normalized = (response_text or "").strip().lower()
    if not normalized:
        return True

    failure_terms = (
        "error",
        "failed",
        "invalid",
        "rejected",
        "unauthorized",
        "denied",
        "mismatch",
    )
    return any(term in normalized for term in failure_terms)


def _parse_gateway_ack(response_text: str) -> tuple[str | None, str | None]:
    """
    Extract gateway request ID and response code from plain text responses like:
    'Message Accepted for Request ID=...~code=API000 & info=...'
    """
    text = response_text or ""
    req_match = re.search(r"Request\s*ID\s*=\s*([^\s~&]+)", text, flags=re.IGNORECASE)
    code_match = re.search(r"code\s*=\s*([A-Za-z0-9_]+)", text, flags=re.IGNORECASE)
    request_id = req_match.group(1).strip() if req_match else None
    code = code_match.group(1).strip().upper() if code_match else None
    return request_id, code


def _format_gateway_mobile_number(phone_number: str) -> str:
    digits_only = "".join(ch for ch in str(phone_number or "") if ch.isdigit())
    if len(digits_only) == 12 and digits_only.startswith("91"):
        return digits_only
    if len(digits_only) == 10:
        return f"91{digits_only}"
    return digits_only


def _normalize_message_for_gateway(message: str) -> str:
    """
    Keep legacy behavior close to vbNewLine-based formatting from old code:
    - Normalize any newline form to CRLF so URL-encoding emits %0D%0A.
    - Replace '&' with 'and' as done in legacy service code.
    """
    normalized = str(message or "").replace("\r\n", "\n").replace("\r", "\n")
    normalized = normalized.replace("\n", "\r\n")
    return normalized.replace("&", "and")

def get_new_otp(phone_number):

    request_limit = int(getattr(settings, "OTP_REQUEST_LIMIT", 15))
    request_window_minutes = int(getattr(settings, "OTP_REQUEST_WINDOW_MINUTES", 15))
    window_start = timezone.now() - timedelta(minutes=request_window_minutes)
    recent_otps_count = OTP.objects.filter(
        phone_number=phone_number,
        created_at__gte=window_start
    ).count()

    if recent_otps_count >= request_limit:
        raise ValueError(
            f"OTP request limit reached ({request_limit} attempts). "
            f"Please try again after {request_window_minutes} minutes."
        )
    
    OTP.objects.filter(
        phone_number=phone_number,
        created_at__lt=window_start,
        used=False
    ).delete()

    otp_value = str(random.randint(1000, 9999))
    otp_obj = OTP.objects.create(phone_number=phone_number, otp=otp_value)
    return otp_obj

@transaction.atomic
def verify_otp(otp_id, phone_number, otp_input):
    try:
        otp_obj = OTP.objects.get(id=otp_id, phone_number=phone_number, used=False)
        if otp_obj.is_expired():
            otp_obj.delete()
            return False, "OTP expired."
        if otp_obj.otp != str(otp_input):
            return False, "Incorrect OTP."
        
        otp_obj.used = True
        otp_obj.save()
        otp_obj.delete()
    
        return True, "OTP verified."
        
    except OTP.DoesNotExist:
        return False, "Invalid OTP or already used."
    

def mark_phone_as_verified(phone_number: str):
    """Mark this phone as verified for 10 minutes"""
    cache.set(f"phone_verified_{phone_number}", True, timeout=600)  # 10 minutes

def is_phone_verified(phone_number: str) -> bool:
    return cache.get(f"phone_verified_{phone_number}") is True

def clear_phone_verified(phone_number: str):
    cache.delete(f"phone_verified_{phone_number}")


def send_otp_via_sms_gateway(phone_number: str, otp_value: str) -> tuple[bool, str]:
    """
    Sends OTP via configured SMS gateway.
    Returns (success, details).
    """
    force_send_in_debug = bool(getattr(settings, "OTP_SMS_FORCE_SEND_IN_DEBUG", False))
    if getattr(settings, "DEBUG", False) and not force_send_in_debug:
        logger.warning(
            "DEBUG mode bypass is enabled and OTP SMS was not sent to %s",
            _mask_phone(phone_number),
        )
        return False, "OTP SMS not sent because DEBUG bypass is active"

    base_url = getattr(settings, "OTP_SMS_BASE_URL", "").strip()
    username = getattr(settings, "OTP_SMS_USERNAME", "").strip()
    # Old service stored encoded pin (`%23` for `#`). Decode once, then urlencode safely.
    pin = unquote(getattr(settings, "OTP_SMS_PIN", "").strip())
    signature = getattr(settings, "OTP_SMS_SIGNATURE", "").strip()
    entity_id = getattr(settings, "OTP_SMS_ENTITY_ID", "").strip()
    template_id = getattr(settings, "OTP_SMS_TEMPLATE_ID", "").strip()

    if not all([base_url, username, pin, signature, entity_id, template_id]):
        logger.error("OTP SMS gateway settings are incomplete")
        return False, "OTP SMS gateway settings are incomplete"

    message_template = getattr(
        settings,
        "OTP_SMS_MESSAGE_TEMPLATE",
        "Your OTP for login is {otp}. Do not share it with anyone."
    )
    message = _normalize_message_for_gateway(message_template.format(otp=otp_value))
    mnumber = _format_gateway_mobile_number(phone_number)

    params = {
        "username": username,
        "pin": pin,
        "message": message,
        "mnumber": mnumber,
        "signature": signature,
        "dlt_entity_id": entity_id,
        "dlt_template_id": template_id,
    }
    if len(message) > 160:
        params["concat"] = "1"

    query = urlencode(
        params,
        quote_via=quote,
    )
    url = f"{base_url}?{query}"

    try:
        verify_ssl = bool(getattr(settings, "OTP_SMS_VERIFY_SSL", True))
        timeout_seconds = int(getattr(settings, "OTP_SMS_TIMEOUT_SECONDS", 10))
        response = requests.get(url, timeout=timeout_seconds, verify=verify_ssl)
        response.raise_for_status()
        response_text = (response.text or "").strip()
        request_id, code = _parse_gateway_ack(response_text)

        # Some gateways return HTTP 200 even for business-level failures.
        # If a code is present, treat non-API000 as failure.
        if (code and code != "API000") or _looks_like_gateway_failure(response_text):
            logger.error(
                "OTP SMS gateway reported failure for %s: %s",
                _mask_phone(phone_number),
                response_text[:300],
            )
            if code:
                return False, f"OTP SMS gateway rejected the request (code={code}, request_id={request_id or 'N/A'})"
            return False, "OTP SMS gateway rejected the request"

        logger.info(
            "OTP SMS sent successfully to %s. Gateway response: %s",
            _mask_phone(phone_number),
            response_text[:300],
        )
        if request_id or code:
            return True, f"OTP accepted by gateway (code={code or 'N/A'}, request_id={request_id or 'N/A'})"
        return True, "OTP SMS sent successfully"
    except requests.RequestException as exc:
        logger.exception("Failed to send OTP SMS to %s: %s", _mask_phone(phone_number), str(exc))
        return False, "Failed to send OTP SMS"
