import secrets
from decimal import Decimal

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import status, serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import (
    WalletBalance,
    WalletTransaction,
    _resolve_module_type_from_license_id,
    _resolve_wallet_row_licensee_id,
)
from .serializers import WalletBalanceSerializer, WalletRechargeCreditSerializer, WalletTransactionSerializer


def _wallet_license_candidates(raw_licensee_id: str):
    value = str(raw_licensee_id or "").strip()
    if not value:
        return []

    out = [value]

    if value.startswith("NLI/"):
        out.append(f"NA/{value[4:]}")
    elif value.startswith("NA/"):
        out.append(f"NLI/{value[3:]}")

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


def _sync_wallet_balance_licensee_from_applicant_license(user, wallet) -> None:
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


def _normalize_wallet_type(wallet_type: str) -> str:
    value = str(wallet_type or "").strip().lower()
    if value in {"education", "educationcess", "education_cess", "education-cess"}:
        return "education_cess"
    return value


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

    scope = str(request.query_params.get("scope") or "").strip().lower()
    if scope == "license":
        qs = qs.filter(wallet_type__in=["license_fee", "security_deposit"])
    elif scope == "wallets":
        qs = qs.exclude(wallet_type__in=["license_fee", "security_deposit"])
    elif scope in {"excise", "education_cess", "hologram"}:
        qs = qs.filter(wallet_type__iexact=scope)

    # Safety net: if balances were not initialized by the workflow signal, initialize them on-demand
    # for the active license and re-query.
    if qs.count() == 0:
        try:
            from models.masters.license.models import License
            from models.transactional.wallet.wallet_initializer import initialize_wallet_balances_for_license

            lic = None
            try:
                na_id = _active_na_license_id_for_applicant(request.user)
                if na_id:
                    lic = (
                        License.objects.filter(applicant=request.user, is_active=True, license_id__iexact=na_id)
                        .order_by("-issue_date", "-license_id")
                        .first()
                    )
            except Exception:
                lic = None

            if lic is None:
                lic = (
                    License.objects.filter(applicant=request.user, is_active=True)
                    .order_by("-issue_date", "-license_id")
                    .first()
                )

            if lic is None and candidates:
                lic = (
                    License.objects.filter(is_active=True)
                    .filter(Q(license_id__in=candidates) | Q(source_object_id__in=candidates))
                    .order_by("-issue_date", "-license_id")
                    .first()
                )

            if lic is not None:
                initialize_wallet_balances_for_license(lic)

                qs = WalletBalance.objects.filter(wallet_filter).order_by("wallet_type", "head_of_account")
                if module_type:
                    qs = qs.filter(module_type__iexact=module_type)
                if scope == "license":
                    qs = qs.filter(wallet_type__in=["license_fee", "security_deposit"])
                elif scope == "wallets":
                    qs = qs.exclude(wallet_type__in=["license_fee", "security_deposit"])
                elif scope in {"excise", "education_cess", "hologram"}:
                    qs = qs.filter(wallet_type__iexact=scope)
        except Exception:
            pass

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

    qs = WalletTransaction.objects.filter(tx_filter, transaction_type__iexact="recharge").order_by("-created_at")

    scope = str(request.query_params.get("scope") or "").strip().lower()
    if scope == "license":
        qs = qs.filter(wallet_type__in=["license_fee", "security_deposit"])
    elif scope == "wallets":
        qs = qs.exclude(wallet_type__in=["license_fee", "security_deposit"])
    elif scope in {"excise", "education_cess", "hologram"}:
        qs = qs.filter(wallet_type__iexact=scope)

    wallet_type = request.query_params.get("wallet_type")
    if wallet_type:
        qs = qs.filter(wallet_type__iexact=wallet_type)

    head_of_account = request.query_params.get("head_of_account")
    if head_of_account:
        qs = qs.filter(head_of_account=head_of_account)

    limit = _safe_limit(request.query_params.get("limit"), default=200)
    qs = qs[:limit]

    return Response({"licensee_id": effective_id, "count": len(qs), "results": WalletTransactionSerializer(qs, many=True).data})


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

    scope = str(request.query_params.get("scope") or "").strip().lower()
    if scope == "license":
        qs = qs.filter(wallet_type__in=["license_fee", "security_deposit"])
    elif scope == "wallets":
        qs = qs.exclude(wallet_type__in=["license_fee", "security_deposit"])
    elif scope in {"excise", "education_cess", "hologram"}:
        qs = qs.filter(wallet_type__iexact=scope)

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

    return Response({"licensee_id": effective_id, "count": len(qs), "results": WalletTransactionSerializer(qs, many=True).data})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def wallet_recharge_credit(request, licensee_id):
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

    existing = WalletTransaction.objects.filter(
        transaction_id=transaction_id,
        transaction_type__iexact="recharge",
        entry_type__iexact="CR",
    ).order_by("-wallet_transaction_id").first()
    if existing:
        return Response(
            {"status": "ok", "already_processed": True, "wallet_transaction": WalletTransactionSerializer(existing).data},
            status=status.HTTP_200_OK,
        )

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
            now_ts = timezone.now()
            template = WalletBalance.objects.select_for_update().filter(wallet_filter).order_by("wallet_balance_id").first()

            template_licensee_id = str(getattr(template, "licensee_id", "") or "").strip() if template else ""
            raw_licensee = template_licensee_id or str(licensee_id or "").strip()
            resolved_licensee_id = _resolve_wallet_row_licensee_id(raw_licensee, request_user or "") or raw_licensee

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
            _sync_wallet_balance_licensee_from_applicant_license(request.user, wallet)

        before = Decimal(str(wallet.current_balance or 0)).quantize(Decimal("0.01"))
        after = (before + amount).quantize(Decimal("0.01"))
        now_ts = timezone.now()
        wallet.current_balance = after
        wallet.total_credit = (Decimal(str(wallet.total_credit or 0)) + amount).quantize(Decimal("0.01"))
        wallet.last_updated_at = now_ts
        wallet.save(update_fields=["current_balance", "total_credit", "last_updated_at"])

        created = WalletTransaction.objects.create(
            wallet_balance=wallet,
            transaction_id=transaction_id,
            licensee_id=str(wallet.licensee_id or "").strip(),
            licensee_name=str(wallet.licensee_name or "").strip() or None,
            user_id=request_user or None,
            module_type=str(wallet.module_type or "other").strip(),
            wallet_type=str(wallet.wallet_type or wallet_type).strip(),
            head_of_account=str(wallet.head_of_account or head_of_account).strip(),
            entry_type="CR",
            transaction_type="recharge",
            amount=amount,
            balance_before=before,
            balance_after=after,
            reference_no=transaction_id,
            source_module="wallet_recharge",
            payment_status="success",
            remarks=remarks,
            created_at=now_ts,
        )

    return Response({"status": "ok", "already_processed": False, "wallet_transaction": WalletTransactionSerializer(created).data})
