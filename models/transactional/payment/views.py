import secrets
import hmac
import hashlib
import ipaddress
from decimal import Decimal
from urllib.parse import quote_plus
from urllib.parse import urlparse

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.http import HttpResponseRedirect
from django.conf import settings
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from .models import (
    PaymentBilldeskTransaction,
    PaymentGatewayParameter,
    PaymentHeadOfAccount,
    PaymentHoaSplit,
    PaymentModule,
    PaymentModuleHoa,
    PaymentStatusMasterBilldesk,
    PaymentWalletTypeHoaMapping,
    PaymentWalletMaster,
    WalletBalance,
    WalletTransaction,
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
    WalletRechargeInitiateSerializer,
    WalletRechargePrepareSerializer,
    WalletBalanceSerializer,
    WalletTransactionSerializer,
)

def _get_auth_status_info(auth_status: str) -> tuple[str, str]:
    code = str(auth_status or "").strip()
    if not code:
        return ("Status not available", "P")

    row = (
        PaymentStatusMasterBilldesk.objects.filter(authstatus=code)
        .only("authstatus_description", "payment_status")
        .first()
    )
    if row and str(row.authstatus_description or "").strip():
        return (
            str(row.authstatus_description).strip(),
            str(row.payment_status or "P").strip().upper() or "P",
        )

    return (f"Unknown status ({code})", "P")


def _get_status_description_by_payment_status(payment_status: str) -> str:
    code = str(payment_status or "").strip().upper()
    if not code:
        return ""

    row = (
        PaymentStatusMasterBilldesk.objects.filter(payment_status=code)
        .exclude(authstatus_description__isnull=True)
        .exclude(authstatus_description__exact="")
        .order_by("authstatus")
        .only("authstatus_description")
        .first()
    )
    if row:
        return str(row.authstatus_description).strip()
    return ""


def _derive_status_description_from_error_description(error_description: str) -> str:
    text = str(error_description or "").strip().lower()
    if not text:
        return ""

    rows = (
        PaymentStatusMasterBilldesk.objects.exclude(authstatus_description__isnull=True)
        .exclude(authstatus_description__exact="")
        .order_by("authstatus")
        .values_list("authstatus_description", flat=True)
    )

    best = ""
    for desc in rows:
        candidate = str(desc or "").strip()
        if not candidate:
            continue
        if candidate.lower() in text and len(candidate) > len(best):
            best = candidate
    return best

def _resolve_license_module_type(raw_licensee_id: str) -> str:
    value = str(raw_licensee_id or "").strip()
    if not value:
        return "distillery"

    try:
        from models.masters.license.models import License
    except Exception:
        return "distillery"

    active_qs = License.objects.filter(is_active=True)
    lic = active_qs.filter(license_id=value).order_by("-issue_date", "-license_id").first()
    if not lic:
        lic = active_qs.filter(source_object_id=value).order_by("-issue_date", "-license_id").first()
    if not lic and value.startswith("NLI/"):
        lic = active_qs.filter(license_id=f"NA/{value[4:]}").order_by("-issue_date", "-license_id").first()
    if not lic and value.startswith("NA/"):
        lic = active_qs.filter(source_object_id=f"NLI/{value[3:]}").order_by("-issue_date", "-license_id").first()

    if not lic:
        return "distillery"

    sub_category = getattr(lic, "license_sub_category", None)
    sub_desc = str(getattr(sub_category, "description", "") or "").strip().lower()
    if "brew" in sub_desc or "beer" in sub_desc:
        return "brewery"
    if "distill" in sub_desc:
        return "distillery"

    sub_category_id = getattr(lic, "license_sub_category_id", None)
    if sub_category_id == 1:
        return "brewery"
    if sub_category_id == 2:
        return "distillery"

    return "distillery"


def _resolve_license_module_type_from_license(lic) -> str:
    if not lic:
        return "distillery"

    sub_category = getattr(lic, "license_sub_category", None)
    sub_desc = str(getattr(sub_category, "description", "") or "").strip().lower()
    if "brew" in sub_desc or "beer" in sub_desc:
        return "brewery"
    if "distill" in sub_desc:
        return "distillery"

    sub_category_id = getattr(lic, "license_sub_category_id", None)
    if sub_category_id == 1:
        return "brewery"
    if sub_category_id == 2:
        return "distillery"

    return "distillery"


def _pick_primary_approved_license(candidates):
    try:
        from models.masters.license.models import License
    except Exception:
        return None

    ids = [str(item or "").strip() for item in (candidates or []) if str(item or "").strip()]
    if not ids:
        return None

    active_qs = License.objects.filter(is_active=True)

    by_license_id = (
        active_qs.filter(license_id__in=ids)
        .select_related("license_sub_category")
        .order_by("-valid_up_to", "-issue_date", "-license_id")
        .first()
    )
    if by_license_id:
        return by_license_id

    by_source_object = (
        active_qs.filter(source_object_id__in=ids)
        .select_related("license_sub_category")
        .order_by("-valid_up_to", "-issue_date", "-license_id")
        .first()
    )
    return by_source_object


def _wallet_type_aliases(wallet_type: str) -> tuple[str, ...]:
    requested = str(wallet_type or "").strip().lower()
    if requested == "excise":
        return ("excise",)
    if requested == "brewery":
        return ("brewery",)
    if requested == "education":
        return ("education", "education_cess", "cess")
    if requested == "hologram":
        return ("hologram",)
    return (requested,)


def _pick_wallet_row(rows, wallet_type: str, module_type: str):
    requested = str(wallet_type or "").strip().lower()
    module = str(module_type or "").strip().lower()
    aliases = _wallet_type_aliases(requested)

    def is_match(row) -> bool:
        row_type = str(getattr(row, "wallet_type", "") or "").strip().lower()
        if not row_type:
            return False
        if requested == "education":
            return row_type in aliases or "education" in row_type
        if requested == "hologram":
            return "hologram" in row_type
        if requested == "excise":
            return row_type == "excise"
        if requested == "brewery":
            return row_type == "brewery"
        return row_type == requested

    matched = [row for row in rows if is_match(row)]
    if not matched:
        return None

    def score(row):
        row_type = str(getattr(row, "wallet_type", "") or "").strip().lower()
        row_module = str(getattr(row, "module_type", "") or "").strip().lower()
        module_priority = 0 if (module and row_module == module) else 1
        alias_priority = 0 if row_type in aliases else 1
        exact_type_priority = 0 if row_type == requested else 1
        row_id = int(getattr(row, "wallet_balance_id", 0) or 0)
        return (module_priority, alias_priority, exact_type_priority, row_id)

    matched.sort(key=score)
    return matched[0]


def _resolve_hoa_from_master(wallet_type: str, module_type: str) -> str:
    requested = str(wallet_type or "").strip().lower()
    module = str(module_type or "").strip().lower()

    mappings = (
        PaymentModuleHoa.objects.filter(is_active="Y")
        .select_related("head_of_account")
        .order_by("id")
    )

    rows = []
    for mapping in mappings:
        hoa_obj = getattr(mapping, "head_of_account", None)
        hoa_code = str(getattr(hoa_obj, "head_of_account", "") or "").strip()
        desc = str(getattr(hoa_obj, "detailed_head_driscription", "") or "").strip().lower()
        if hoa_code:
            rows.append((hoa_code, desc))

    if not rows:
        return ""

    def matches(hoa_desc: str) -> bool:
        if requested == "education":
            return "education" in hoa_desc
        if requested == "hologram":
            return "hologram" in hoa_desc
        if requested == "excise":
            return "excise" in hoa_desc
        if requested == "brewery":
            return "brew" in hoa_desc or "beer" in hoa_desc
        return False

    filtered = [row for row in rows if matches(row[1])]
    if not filtered:
        return rows[0][0]

    if requested == "excise":
        distillery_rows = [row for row in filtered if "distill" in row[1]]
        if distillery_rows:
            return distillery_rows[0][0]
    if requested == "brewery":
        brewery_rows = [row for row in filtered if "brew" in row[1] or "beer" in row[1]]
        if brewery_rows:
            return brewery_rows[0][0]

    return filtered[0][0]


def _resolve_hoa_from_mapping(wallet_type: str, module_type: str) -> str:
    requested = str(wallet_type or "").strip().lower()
    module = str(module_type or "").strip().lower()
    aliases = _wallet_type_aliases(requested)

    qs = PaymentWalletTypeHoaMapping.objects.filter(is_active="Y")
    if module:
        by_module = list(
            qs.filter(module_type__iexact=module).order_by("id")
        )
    else:
        by_module = []

    candidates = by_module if by_module else list(qs.order_by("id"))
    if not candidates:
        return ""

    for row in candidates:
        row_wallet_type = str(getattr(row, "wallet_type", "") or "").strip().lower()
        if row_wallet_type in aliases:
            return str(getattr(row, "head_of_account", "") or "").strip()

    return ""


def _resolve_wallet_context(licensee_id: str, wallet_type: str) -> dict:
    requested_wallet_type = str(wallet_type or "").strip().lower()
    candidates = _wallet_license_candidates(licensee_id)
    if not candidates:
        candidates = [str(licensee_id or "").strip()]

    primary_license = _pick_primary_approved_license(candidates)
    if primary_license and str(getattr(primary_license, "license_id", "")).strip():
        canonical_license_id = str(primary_license.license_id).strip()
        if canonical_license_id not in candidates:
            candidates = [canonical_license_id, *candidates]
        module_type = _resolve_license_module_type_from_license(primary_license)
    else:
        module_type = _resolve_license_module_type(candidates[0])
    effective_wallet_type = requested_wallet_type
    if requested_wallet_type in ("excise", "brewery"):
        effective_wallet_type = "brewery" if module_type == "brewery" else "excise"

    wallet_rows = list(
        WalletBalance.objects.filter(licensee_id__in=candidates).order_by("wallet_balance_id")
    )
    wallet = _pick_wallet_row(wallet_rows, effective_wallet_type, module_type)
    expected_hoa = _resolve_hoa_from_mapping(effective_wallet_type, module_type)
    if not expected_hoa:
        expected_hoa = str(getattr(wallet, "head_of_account", "") or "").strip()
    if not expected_hoa:
        expected_hoa = _resolve_hoa_from_master(effective_wallet_type, module_type)

    payer_id = str(getattr(wallet, "licensee_id", "") or "").strip() or candidates[0]

    return {
        "payer_id": payer_id,
        "module_type": module_type,
        "wallet_type": effective_wallet_type,
        "head_of_account": expected_hoa,
        "wallet_row": wallet,
    }


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


def _generate_transaction_id() -> str:
    return timezone.now().strftime("TXN%Y%m%d%H%M%S%f")


def _generate_unique_utr() -> str:
    for _ in range(10):
        utr = f"UTR{timezone.now().strftime('%Y%m%d%H%M%S')}{secrets.token_hex(4).upper()}"
        if not PaymentBilldeskTransaction.objects.filter(pk=utr).exists():
            return utr
    raise RuntimeError("Unable to generate unique UTR")


def _generate_wallet_transaction_id(wallet_type: str) -> str:
    prefix_map = {
        "excise": "EX",
        "brewery": "BR",
        "education": "EC",
        "hologram": "HG",
    }
    prefix = prefix_map.get(str(wallet_type or "").strip().lower(), "EX")

    for _ in range(20):
        candidate = f"BILLDESK{prefix}{timezone.now().strftime('%y%m%d%H%M%S%f')}{secrets.token_hex(2).upper()}"
        exists = WalletTransaction.objects.filter(transaction_id=candidate).exists()
        if not exists:
            return candidate
    raise RuntimeError("Unable to generate unique wallet transaction id")


def _sanitize_billdesk_field(value: str) -> str:
    """
    Sanitize field values for BillDesk to prevent WAF rejection.
    Removes special characters that commonly trigger security filters.
    """
    if not value or value == "NA":
        return value
    
    # Remove special characters that trigger WAF
    # Keep only alphanumeric, spaces, dots, hyphens, and forward slashes
    import re
    sanitized = re.sub(r'[!@#$%\^&*\(\)\+=\\\{\}\[\]\|:;,\"\'<>\?\~`]', '', value)
    # Replace multiple spaces with single space
    sanitized = re.sub(r'\s+', ' ', sanitized)
    # Trim whitespace
    sanitized = sanitized.strip()
    # Limit length to 30 characters for additional info fields
    if len(sanitized) > 30:
        sanitized = sanitized[:30]
    
    return sanitized if sanitized else "NA"


def _build_billdesk_request_message(
    *,
    gateway: PaymentGatewayParameter,
    utr: str,
    amount: Decimal,
    addl1: str,
    addl2: str,
    addl3: str,
    addl4: str,
    addl5: str,
    addl6: str,
    addl7: str,
    return_url: str,
) -> tuple[str, str]:
    # Sanitize all additional info fields to prevent WAF rejection
    addl1 = _sanitize_billdesk_field(addl1)
    addl2 = _sanitize_billdesk_field(addl2)
    addl3 = _sanitize_billdesk_field(addl3)
    addl4 = _sanitize_billdesk_field(addl4)
    addl5 = _sanitize_billdesk_field(addl5)
    addl6 = _sanitize_billdesk_field(addl6)
    addl7 = _sanitize_billdesk_field(addl7)
    
    msg_string = (
        f"{gateway.merchantid}|{utr}|NA|{Decimal(amount):0.2f}|NA|NA|NA|INR|NA|R|{gateway.securityid}|NA|NA|F|"
        f"{addl1}|{addl2}|{addl3}|{addl4}|{addl5}|{addl6}|{addl7}|{return_url}"
    )
    digest = hmac.new(
        (gateway.encryption_key or "").encode("utf-8"),
        msg_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest().upper()
    return msg_string, digest


def _is_public_callback_url(raw_url: str) -> bool:
    allow_private = bool(getattr(settings, "BILLDESK_ALLOW_PRIVATE_CALLBACK", False))
    if allow_private:
        return True

    value = str(raw_url or "").strip()
    if not value:
        return False
    try:
        parsed = urlparse(value)
    except Exception:
        return False

    if parsed.scheme not in ("http", "https"):
        return False

    host = str(parsed.hostname or "").strip().lower()
    if not host:
        return False
    if host in ("localhost", "127.0.0.1", "0.0.0.0", "::1"):
        return False

    try:
        ip = ipaddress.ip_address(host)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            return False
    except ValueError:
        # Non-IP hostnames are allowed.
        pass

    return True


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
def wallet_summary(request, licensee_id):
    module_type = request.query_params.get("module_type")
    candidates = _wallet_license_candidates(licensee_id)
    if not candidates:
        candidates = [str(licensee_id or "").strip()]
    qs = WalletBalance.objects.filter(licensee_id__in=candidates).order_by("wallet_type", "head_of_account")
    if module_type:
        qs = qs.filter(module_type__iexact=module_type)

    total = sum((row.current_balance for row in qs), Decimal("0.00"))
    return Response(
        {
            "licensee_id": licensee_id,
            "total_wallet_amount": total,
            "count": qs.count(),
            "results": WalletBalanceSerializer(qs, many=True).data,
        }
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def wallet_recharge_list(request, licensee_id):
    candidates = _wallet_license_candidates(licensee_id)
    if not candidates:
        candidates = [str(licensee_id or "").strip()]
    qs = (
        WalletTransaction.objects.filter(
            licensee_id__in=candidates,
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
            "licensee_id": licensee_id,
            "count": len(qs),
            "results": WalletTransactionSerializer(qs, many=True).data,
        }
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def wallet_history_list(request, licensee_id):
    candidates = _wallet_license_candidates(licensee_id)
    if not candidates:
        candidates = [str(licensee_id or "").strip()]
    qs = WalletTransaction.objects.filter(licensee_id__in=candidates).order_by("-created_at")

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
            "licensee_id": licensee_id,
            "count": len(qs),
            "results": WalletTransactionSerializer(qs, many=True).data,
        }
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def payment_transaction_list(request):
    qs = PaymentBilldeskTransaction.objects.all().order_by("-transaction_date")

    if request.query_params.get("payer_id"):
        candidates = _wallet_license_candidates(request.query_params["payer_id"])
        if not candidates:
            candidates = [str(request.query_params["payer_id"] or "").strip()]
        qs = qs.filter(payer_id__in=candidates)
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
def wallet_recharge_prepare(request):
    serializer = WalletRechargePrepareSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    data = serializer.validated_data
    context = _resolve_wallet_context(data["licensee_id"], data["wallet_type"])

    transaction_id = _generate_wallet_transaction_id(context["wallet_type"])

    return Response(
        {
            "status": "ok",
            "licensee_id": context["payer_id"],
            "wallet_type": context["wallet_type"],
            "module_type": context["module_type"],
            "wallet_transaction_id": transaction_id,
            "head_of_account": context["head_of_account"],
        }
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def wallet_recharge_initiate(request):
    serializer = WalletRechargeInitiateSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    data = serializer.validated_data
    context = _resolve_wallet_context(data["licensee_id"], data["wallet_type"])
    if str(context["head_of_account"] or "").strip() == "":
        return Response({"detail": "Wallet HOA is not configured."}, status=status.HTTP_400_BAD_REQUEST)

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

    hoa_row = (
        PaymentHeadOfAccount.objects.filter(head_of_account=context["head_of_account"])
        .only("major_head", "minor_head", "detailed_head", "detailed_head_driscription")
        .first()
    )
    addl1 = "NA"
    addl3 = "NA"
    if hoa_row:
        major = str(hoa_row.major_head or "").strip()
        minor = str(hoa_row.minor_head or "").strip()
        detailed = str(hoa_row.detailed_head or "").strip()
        if major and minor and detailed:
            addl1 = f"{major}.{minor}.{detailed}"
        desc = str(hoa_row.detailed_head_driscription or "").strip()
        if desc:
            addl3 = desc[:30]
    else:
        hoa_parts = str(context["head_of_account"]).split("-")
        if len(hoa_parts) >= 5:
            addl1 = f"{hoa_parts[0]}.{hoa_parts[2]}.{hoa_parts[4]}"

    addl2 = "SIKPAY"
    addl4 = "NA"
    addl5 = "NA"
    addl6 = "NA"
    addl7 = "NA"

    configured_public_callback = str(getattr(settings, "BILLDESK_PUBLIC_CALLBACK_URL", "") or "").strip()
    default_callback_url = (
        configured_public_callback
        or request.build_absolute_uri("/transactional/payment/billdesk/response/")
    )
    requested_return_url = str(data.get("return_url") or "").strip()
    configured_return_url = str(gateway.return_url or "").strip()
    configured_path = configured_return_url.lower()
    configured_looks_like_frontend = (
        "/payment/billdesk-handler" in configured_path
        or "/payment/billdesk-response-landing" in configured_path
        or "/payment/callback" in configured_path
    )
    configured_looks_like_backend_callback = "/billdesk/response" in configured_path
    return_url = requested_return_url
    if not return_url:
        if configured_return_url and configured_looks_like_backend_callback and not configured_looks_like_frontend:
            return_url = configured_return_url
        else:
            return_url = default_callback_url
    if not return_url:
        return Response(
            {"detail": "Return URL is not configured in gateway parameters."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if not _is_public_callback_url(return_url):
        return Response(
            {
                "detail": (
                    "Invalid BillDesk callback URL. Configure a public callback URL "
                    "(not localhost/127.x/private IP) in eabgari_payment_gateway_parameters.return_url "
                    "or settings.BILLDESK_PUBLIC_CALLBACK_URL."
                ),
                "callback_url": return_url,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    amount = data["amount"]
    utr = _generate_unique_utr()
    request_user_id = getattr(request.user, "username", "") or ""
    transaction_id = str(data["wallet_transaction_id"]).strip()

    if WalletTransaction.objects.filter(transaction_id=transaction_id).exists():
        return Response(
            {"detail": "Wallet Transaction ID already exists. Generate a new one."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    request_msg_without_checksum, checksum = _build_billdesk_request_message(
        gateway=gateway,
        utr=utr,
        amount=amount,
        addl1=addl1,
        addl2=addl2,
        addl3=addl3,
        addl4=addl4,
        addl5=addl5,
        addl6=addl6,
        addl7=addl7,
        return_url=return_url,
    )
    request_msg = f"{request_msg_without_checksum}|{checksum}"

    with transaction.atomic():
        PaymentBilldeskTransaction.objects.create(
            utr=utr,
            transaction_id_no_hoa=transaction_id,
            payer_id=context["payer_id"],
            payment_module_code="999",
            transaction_amount=amount,
            request_merchantid=gateway.merchantid,
            request_currencytype="INR",
            request_typefield1="R",
            request_securityid=gateway.securityid,
            request_typefield2="F",
            request_additionalinfo1=addl1,
            request_additionalinfo2=addl2,
            request_additionalinfo3=addl3,
            request_additionalinfo4=addl4,
            request_additionalinfo5=addl5,
            request_additionalinfo6=addl6,
            request_additionalinfo7=addl7,
            request_return_url=return_url,
            request_checksum=checksum,
            request_string=request_msg,
            payment_status="P",
            user_id=request_user_id,
            opr_date=timezone.now(),
        )

        PaymentHoaSplit.objects.create(
            transaction_id_no=transaction_id,
            head_of_account=context["head_of_account"],
            payer_id=context["payer_id"],
            amount=amount,
            payment_module_code="999",
            requisition_id_no=None,
            user_id=request_user_id,
            opr_date=timezone.now(),
        )

    return Response(
        {
            "status": "ok",
            "wallet_transaction_id": transaction_id,
            "utr": utr,
            "amount": amount,
            "head_of_account": context["head_of_account"],
            "wallet_type": context["wallet_type"],
            "gateway": {
                "sl_no": gateway.sl_no,
                "name": gateway.payment_gateway_name,
                "merchantid": gateway.merchantid,
                "return_url": return_url,
            },
            "msg": request_msg,
            "options": "NA",
            "callback_url": return_url,
        },
        status=status.HTTP_201_CREATED,
    )


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


@api_view(["POST", "GET"])
@permission_classes([AllowAny])
def billdesk_response_callback(request):
    frontend_base = getattr(settings, "FRONTEND_URL", "http://localhost:4200")

    msg = ""
    if request.method == "POST":
        msg = str(request.data.get("msg") or request.POST.get("msg") or "").strip()
    else:
        msg = str(request.query_params.get("msg") or "").strip()

    if not msg:
        return HttpResponseRedirect(
            f"{frontend_base}/payment/billdesk-response-landing?status=F&message="
            + quote_plus("Response not received from bank site")
        )

    parts = msg.split("|")
    if len(parts) < 26:
        return HttpResponseRedirect(
            f"{frontend_base}/payment/billdesk-response-landing?status=F&message="
            + quote_plus("Invalid BillDesk response")
        )

    utr = str(parts[1] or "").strip()
    if not utr:
        return HttpResponseRedirect(
            f"{frontend_base}/payment/billdesk-response-landing?status=F&message="
            + quote_plus("UTR missing in response")
        )

    txn = PaymentBilldeskTransaction.objects.filter(pk=utr).first()
    if not txn:
        return HttpResponseRedirect(
            f"{frontend_base}/payment/billdesk-response-landing?status=F&message="
            + quote_plus("Transaction not found")
        )

    request_merchant_id = str(parts[0] or "").strip()
    auth_status = str(parts[14] or "").strip()
    error_status = str(parts[23] or "").strip()
    error_description = str(parts[24] or "").strip()
    checksum_received = str(parts[25] or "").strip().upper()

    checksum_source = "|".join(parts[:-1])
    gateway = (
        PaymentGatewayParameter.objects.filter(
            is_active="Y",
            merchantid=request_merchant_id,
        )
        .order_by("sl_no")
        .first()
    )
    if not gateway:
        gateway = PaymentGatewayParameter.objects.filter(is_active="Y").order_by("sl_no").first()

    checksum_valid = False
    checksum_calculated = ""
    if gateway:
        checksum_calculated = hmac.new(
            (gateway.encryption_key or "").encode("utf-8"),
            checksum_source.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest().upper()
        checksum_valid = checksum_calculated == checksum_received

    if not checksum_valid:
        txn.payment_status = "F"
        txn.response_string = msg
        txn.response_authstatus = auth_status
        txn.response_errorstatus = error_status or "CHECKSUM_ERROR"
        txn.response_errordescription = error_description or "Checksum validation failed"
        txn.response_checksum = checksum_received
        txn.response_checksum_calculated = checksum_calculated
        txn.opr_date = timezone.now()
        txn.save()
        details = quote_plus(error_description or "Checksum validation failed")
        return HttpResponseRedirect(
            f"/payment/billdesk-response-landing?utr={quote_plus(utr)}&status=F"
            f"&message={quote_plus('Payment failed')}"
            f"&reason={quote_plus('Response checksum validation failed')}"
            f"&details={details}"
            f"&authStatus={quote_plus(auth_status or 'NA')}"
            f"&errorCode={quote_plus(error_status or 'CHECKSUM_ERROR')}"
        )

    reason, mapped_payment_status = _get_auth_status_info(auth_status)
    payment_status = "S" if mapped_payment_status == "S" else "F"

    txn.response_string = msg
    txn.response_merchantid = request_merchant_id
    txn.response_customerid = str(parts[1] or "").strip()
    txn.response_txnreferenceno = str(parts[2] or "").strip()
    txn.response_bankreferenceno = str(parts[3] or "").strip()
    try:
        txn.response_txnamount = Decimal(str(parts[4] or "0").strip() or "0")
    except Exception:
        pass
    txn.response_bankid = str(parts[5] or "").strip()
    txn.response_bankmerchantid = str(parts[6] or "").strip()
    txn.response_txntype = str(parts[7] or "").strip()
    txn.response_currencyname = str(parts[8] or "").strip()
    txn.response_itemcode = str(parts[9] or "").strip()
    txn.response_securitytype = str(parts[10] or "").strip()
    txn.response_securityid = str(parts[11] or "").strip()
    txn.response_securitypassword = str(parts[12] or "").strip()
    txn.response_authstatus = auth_status
    txn.response_settlementtype = str(parts[15] or "").strip()
    txn.response_additionalinfo1 = str(parts[16] or "").strip()
    txn.response_additionalinfo2 = str(parts[17] or "").strip()
    txn.response_additionalinfo3 = str(parts[18] or "").strip()
    txn.response_additionalinfo4 = str(parts[19] or "").strip()
    txn.response_additionalinfo5 = str(parts[20] or "").strip()
    txn.response_additionalinfo6 = str(parts[21] or "").strip()
    txn.response_additionalinfo7 = str(parts[22] or "").strip()
    txn.response_errorstatus = error_status
    txn.response_errordescription = error_description
    txn.response_checksum = checksum_received
    txn.response_checksum_calculated = checksum_calculated
    txn.response_initial_authstatus = auth_status
    txn.response_initial_datetime = timezone.now()
    txn.payment_status = payment_status
    txn.opr_date = timezone.now()
    txn.save()

    is_success = payment_status == "S"
    txn_ref = str(parts[2] or "").strip()
    bank_ref = str(parts[3] or "").strip()
    derived_reason = _derive_status_description_from_error_description(error_description)
    if derived_reason:
        reason = derived_reason
    elif not is_success and auth_status == "NA":
        reason = _get_status_description_by_payment_status("F") or reason

    is_user_cancel_like = (
        not is_success
        and mapped_payment_status == "P"
        and not txn_ref
        and not bank_ref
    )
    if is_user_cancel_like:
        reason = (
            _get_auth_status_info("NA")[0]
            or _get_status_description_by_payment_status("P")
            or reason
        )

    details = error_description or (
        "Payment captured successfully"
        if is_success
        else (
            (_get_status_description_by_payment_status("P") or "Payment pending")
            if is_user_cancel_like
            else "No additional error description from bank"
        )
    )
    message = "Payment successful" if is_success else "Payment failed"
    return HttpResponseRedirect(
        f"{frontend_base}/payment/billdesk-response-landing?utr={quote_plus(utr)}"
        f"&status={quote_plus(payment_status)}"
        f"&message={quote_plus(message)}"
        f"&reason={quote_plus(reason)}"
        f"&details={quote_plus(details)}"
        f"&authStatus={quote_plus(auth_status or 'NA')}"
        f"&errorCode={quote_plus(error_status or '')}"
        f"&txnRef={quote_plus(txn_ref)}"
        f"&bankRef={quote_plus(bank_ref)}"
    )
