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
    SecurityDepositRecord,
    _resolve_module_type_from_license_id,
    _resolve_wallet_row_licensee_id,
)
from .serializers import (
    WalletBalanceSerializer,
    WalletRechargeCreditSerializer,
    WalletTransactionSerializer,
    SecurityDepositRecordSerializer,
)
from .wallet_service import credit_wallet_balance, debit_wallet_balance


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
        if hasattr(request.user, "manufacturing_units"):
            unit_ids = list(
                request.user.manufacturing_units.exclude(licensee_id__isnull=True)
                .exclude(licensee_id="")
                .values_list("licensee_id", flat=True)
            )
            for unit_id in unit_ids:
                candidates.extend(_wallet_license_candidates(unit_id))
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

    # Use all license id variants (NA/NLI + related active licenses) so the balance updates
    # immediately even when different endpoints/clients send different id formats.
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
        qs = qs.filter(wallet_type__code__in=["license_fee", "security_deposit"])
    elif scope == "wallets":
        qs = qs.exclude(wallet_type__code__in=["license_fee", "security_deposit"])
    elif scope in {"excise", "education_cess", "hologram", "additional_excise"}:
        matching_codes = [scope]
        if scope == "excise":
            matching_codes = ["excise", "additional_excise", "additional_ed"]
        qs = qs.filter(wallet_type__code__in=matching_codes)

    wallet_type = request.query_params.get("wallet_type")
    if wallet_type:
        wallet_type = _normalize_wallet_type(wallet_type)
        matching_codes = [wallet_type]
        if wallet_type == "excise":
            matching_codes = ["excise", "additional_excise", "additional_ed"]
        qs = qs.filter(wallet_type__code__in=matching_codes)

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

    try:
        wallet_txn, _, already_processed = credit_wallet_balance(
            transaction_id=transaction_id,
            licensee_id=str(licensee_id or "").strip(),
            wallet_type=wallet_type,
            head_of_account=head_of_account,
            amount=amount,
            entry_type="CR",
            transaction_type="recharge",
            user_id=request_user,
            source_module="wallet_recharge",
            payment_status="success",
            remarks=remarks,
        )
    except ValueError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    if not wallet_txn:
        return Response({"detail": "Unable to record wallet recharge."}, status=status.HTTP_400_BAD_REQUEST)

    if wallet_type == "security_deposit":
        try:
            from django.db.models import Q
            from django.contrib.contenttypes.models import ContentType
            from models.masters.license.models import License
            from models.transactional.company_collaboration.models import CompanyCollaboration
            from models.transactional.new_license_application.models import NewLicenseApplication
            from models.transactional.new_license_application.payment_status import sync_new_license_payment_status
            from models.transactional.new_license_application.views import (
                _resolve_license_fee_row,
                _get_additional_charge_total,
            )
            from models.transactional.wallet.wallet_service import debit_wallet_balance

            user = request.user
            if not user or not user.is_authenticated:
                from auth.user.models import CustomUser
                username = str(getattr(request, "user", "") or "").strip()
                user = CustomUser.objects.filter(username__iexact=username).first()

            candidates = _wallet_candidates_for_request(request, licensee_id)
            lic = License.objects.filter(license_id__in=candidates).order_by("-issue_date", "-license_id").first()
            application = None
            if lic and lic.source_type == "new_license_application":
                application = NewLicenseApplication.objects.filter(application_id=lic.source_object_id).first()

            # Fallback logic for NewLicenseApplication
            if not application or getattr(application, "is_approved", False) or getattr(application, "is_security_fee_paid", False):
                if not user and lic:
                    user = getattr(lic, "applicant", None)

                if user and user.is_authenticated:
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

                try:
                    from models.transactional.wallet.wallet_service import create_or_update_security_deposit_record
                    create_or_update_security_deposit_record(
                        application=application,
                        user=user,
                        amount=amount,
                        transaction_id=transaction_id,
                        reference_no=application.application_id,
                        remarks="Wallet recharge security deposit credit",
                    )
                except Exception as sd_err:
                    logger.warning("Failed to create security deposit record from wallet recharge: %s", sd_err)

                sync_new_license_payment_status(application)
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error("Auto security fee payment failed: %s", str(e), exc_info=True)

    return Response(
        {"status": "ok", "already_processed": already_processed, "wallet_transaction": WalletTransactionSerializer(wallet_txn).data},
        status=status.HTTP_200_OK,
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def security_deposit_record_list(request):
    """
    List and filter all SecurityDepositRecords with search, status filtering, date range,
    pagination and summary statistics for Site Admin.
    """
    from django.db.models import Sum, Count
    from .serializers import SecurityDepositRecordSerializer

    qs = SecurityDepositRecord.objects.all().order_by("-payment_date", "-created_at")

    user = request.user
    role_name = str(getattr(getattr(user, "role", None), "name", "") or getattr(user, "role", "") or "").strip().lower()
    role_clean = role_name.replace(" ", "").replace("_", "").replace("-", "")
    is_admin = bool(
        getattr(user, "is_superuser", False)
        or getattr(user, "is_staff", False)
        or any(k in role_clean for k in ("admin", "commissioner", "secretary", "oic", "officer", "inspector", "clerk"))
        or (role_clean and role_clean not in ("licensee", "distributor", "applicant", "salesman", "barman"))
    )
    if not is_admin:
        qs = qs.filter(Q(user=user) | Q(username__iexact=user.username) | Q(applicant_user_id=str(user.pk)))

    # Query / Search filter
    search = request.query_params.get("search") or request.query_params.get("q")
    if search:
        s = search.strip()
        qs = qs.filter(
            Q(username__icontains=s)
            | Q(applicant_name__icontains=s)
            | Q(applicant_user_id__icontains=s)
            | Q(application_id__icontains=s)
            | Q(license_id__icontains=s)
            | Q(reference_no__icontains=s)
            | Q(transaction_id__icontains=s)
            | Q(establishment_name__icontains=s)
        )

    # Status filter
    status_filter = request.query_params.get("status")
    if status_filter and status_filter.strip().lower() != "all":
        qs = qs.filter(status__iexact=status_filter.strip())

    # Date range filters
    from_date = request.query_params.get("from_date")
    to_date = request.query_params.get("to_date")
    if from_date:
        try:
            qs = qs.filter(from_date__gte=from_date.strip())
        except Exception:
            pass
    if to_date:
        try:
            qs = qs.filter(to_date__lte=to_date.strip())
        except Exception:
            pass

    # Compute stats on the filtered queryset
    stats = {
        "total_deposit_amount": float(qs.aggregate(total=Sum("amount"))["total"] or 0.00),
        "total_balance_amount": float(qs.aggregate(total=Sum("balance_amount"))["total"] or 0.00),
        "total_deducted_amount": float(qs.aggregate(total=Sum("refunded_amount"))["total"] or 0.00),
        "total_records_count": qs.count(),
        "total_active_count": qs.filter(status="PAID").count(),
        "total_deducted_count": qs.filter(status__in=["DEDUCTED", "FORFEITED"]).count(),
        "total_refunded_count": qs.filter(status="REFUNDED").count(),
    }

    # Pagination
    page_raw = request.query_params.get("page")
    page_size_raw = request.query_params.get("page_size") or request.query_params.get("limit")
    try:
        page = int(page_raw) if page_raw is not None else 1
        page_size = int(page_size_raw) if page_size_raw is not None else 50
    except (ValueError, TypeError):
        page = 1
        page_size = 50

    page = max(1, page)
    page_size = max(1, min(page_size, 200))
    total_count = qs.count()
    offset = (page - 1) * page_size
    items = qs[offset : offset + page_size]

    serializer = SecurityDepositRecordSerializer(items, many=True)
    return Response({
        "stats": stats,
        "count": total_count,
        "page": page,
        "page_size": page_size,
        "total_pages": (total_count + page_size - 1) // page_size if page_size > 0 else 1,
        "results": serializer.data,
    })


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def deduct_security_deposit(request, pk):
    """
    Deduct/forfeit a licensee's security deposit amount.
    When executed:
    1. Deducts amount from SecurityDepositRecord and updates status to DEDUCTED.
    2. Sets NewLicenseApplication.is_security_fee_paid = False and is_approved = False.
    3. Deactivates the License (is_active = False - Suspended).
    4. Debits the security deposit wallet balance and records a DR transaction.
    5. Writes an audit entry in AdminLog.
    """
    import logging
    from .serializers import SecurityDepositRecordSerializer
    from .wallet_service import debit_wallet_balance
    logger = logging.getLogger(__name__)

    try:
        record = SecurityDepositRecord.objects.select_for_update().get(pk=pk)
    except SecurityDepositRecord.DoesNotExist:
        return Response({"detail": "Security deposit record not found."}, status=status.HTTP_404_NOT_FOUND)

    raw_deduct_amount = request.data.get("deduct_amount") or request.data.get("amount")
    remarks = str(request.data.get("remarks") or request.data.get("reason") or "Security deposit deducted by admin").strip()
    action_type = str(request.data.get("action_type") or "DEDUCTED").upper()
    if action_type not in ("DEDUCTED", "FORFEITED"):
        action_type = "DEDUCTED"

    current_balance = Decimal(str(record.balance_amount or record.amount or 0)).quantize(Decimal("0.01"))
    if current_balance <= Decimal("0.00"):
        return Response(
            {"detail": "No balance left to deduct in this security deposit record."},
            status=status.HTTP_400_BAD_REQUEST
        )

    if raw_deduct_amount is not None and str(raw_deduct_amount).strip():
        try:
            deduct_amt = Decimal(str(raw_deduct_amount)).quantize(Decimal("0.01"))
            if deduct_amt <= Decimal("0.00"):
                return Response({"detail": "Deduction amount must be greater than zero."}, status=status.HTTP_400_BAD_REQUEST)
            if deduct_amt > current_balance:
                return Response(
                    {"detail": f"Deduction amount (₹{deduct_amt}) cannot exceed available balance (₹{current_balance})."},
                    status=status.HTTP_400_BAD_REQUEST
                )
        except Exception as exc:
            return Response({"detail": f"Invalid deduction amount: {exc}"}, status=status.HTTP_400_BAD_REQUEST)
    else:
        deduct_amt = current_balance

    with transaction.atomic():
        # 1. Update SecurityDepositRecord
        old_refunded = Decimal(str(record.refunded_amount or 0)).quantize(Decimal("0.01"))
        record.refunded_amount = old_refunded + deduct_amt
        record.balance_amount = max(Decimal("0.00"), record.amount - record.refunded_amount)
        record.status = action_type
        record.to_date = timezone.now().date()
        admin_info = f"Deducted ₹{deduct_amt} by {request.user.username} on {timezone.now().strftime('%d-%m-%Y %H:%M')}. Reason: {remarks}"
        if record.remarks:
            record.remarks = f"{record.remarks}\n[{admin_info}]"
        else:
            record.remarks = admin_info
        record.save()

        # 2. Update NewLicenseApplication: current_stage = Terminated, is_security_fee_paid = False, is_approved = False
        app_updated = False
        to_stage_name = "Terminated"
        try:
            from models.transactional.new_license_application.models import NewLicenseApplication
            from auth.workflow.models import WorkflowStage, Transaction as WorkflowTransaction
            from django.contrib.contenttypes.models import ContentType

            app = None
            if record.application_id:
                app = NewLicenseApplication.objects.select_related("current_stage", "workflow").filter(application_id=record.application_id).first()
            if not app and record.user:
                app = NewLicenseApplication.objects.select_related("current_stage", "workflow").filter(applicant=record.user).first()

            if app:
                old_stage = app.current_stage
                wf = app.workflow
                term_stage, _ = WorkflowStage.objects.get_or_create(
                    workflow=wf,
                    name="Terminated",
                    defaults={
                        "description": "Application terminated and security deposit deducted/forfeited",
                        "is_final": True,
                        "is_initial": False,
                    }
                )
                app.current_stage = term_stage
                app.is_security_fee_paid = False
                app.is_approved = False
                app.save(update_fields=["current_stage", "is_security_fee_paid", "is_approved", "updated_at"])
                app_updated = True

                # Record polymorphic workflow transaction
                try:
                    ct = ContentType.objects.get_for_model(app)
                    WorkflowTransaction.objects.create(
                        content_type=ct,
                        object_id=str(app.application_id),
                        stage=term_stage,
                        remarks=f"Security deposit deducted ({deduct_amt}). License suspended and application moved to Terminated stage. Reason: {remarks}",
                        performed_by=request.user if request.user and request.user.is_authenticated else None,
                    )
                except Exception as txn_err:
                    logger.warning("Failed to create workflow Transaction on termination: %s", txn_err)
        except Exception as app_err:
            logger.error("Error updating NewLicenseApplication on security deposit deduction: %s", app_err, exc_info=True)

        # 3. Deactivate License (is_active = False)
        license_suspended = False
        license_id_str = record.license_id or ""
        try:
            from models.masters.license.models import License
            lic = None
            if record.license_id:
                lic = License.objects.filter(license_id=record.license_id).first()
            if not lic and record.application_id:
                lic = License.objects.filter(source_object_id=record.application_id).first()
            if not lic and record.user:
                lic = License.objects.filter(applicant=record.user, is_active=True).first()
            if lic:
                lic.is_active = False
                lic.save(update_fields=["is_active"])
                license_suspended = True
                license_id_str = lic.license_id
        except Exception as lic_err:
            logger.error("Error deactivating License on security deposit deduction: %s", lic_err, exc_info=True)

        # 4. Debit Wallet Balance (security_deposit wallet)
        wallet_debited = False
        try:
            target_licensee_id = record.license_id or record.application_id or str(record.user_id or "")
            txn_id = f"DED-SD-{record.pk}-{int(timezone.now().timestamp())}"
            wallet_txn, w_bal, _ = debit_wallet_balance(
                transaction_id=txn_id,
                licensee_id=target_licensee_id,
                wallet_type="security_deposit",
                head_of_account="non",
                amount=deduct_amt,
                user_id=record.username or str(record.user_id or ""),
                licensee_name=record.applicant_name or record.establishment_name or "",
                source_module="security_deposit_deduction",
                remarks=remarks,
                transaction_type="deduction",
            )
            if wallet_txn:
                wallet_debited = True
        except Exception as w_err:
            logger.warning("Could not debit security deposit wallet balance: %s", w_err)

        # 5. Log in AdminLog
        try:
            from models.transactional.logs.services import log_admin_action
            log_admin_action(
                user=request.user,
                module_name="Security Deposit Master",
                application_id=record.application_id or record.license_id or f"SD-{record.pk}",
                action="DEDUCT_SECURITY_DEPOSIT",
                remarks=f"Deducted ₹{deduct_amt} from Security Deposit. License {'suspended' if license_suspended else 'marked inactive'}. Reason: {remarks}",
                status="COMPLETED",
                metadata={
                    "security_deposit_record_id": record.pk,
                    "deduct_amount": float(deduct_amt),
                    "remaining_balance": float(record.balance_amount),
                    "license_suspended": license_suspended,
                    "license_id": license_id_str,
                    "application_updated": app_updated,
                    "wallet_debited": wallet_debited,
                }
            )
        except Exception as log_err:
            logger.error("Error creating AdminLog for security deposit deduction: %s", log_err)

    return Response({
        "status": "success",
        "message": f"Successfully deducted ₹{deduct_amt} from Security Deposit. License has been suspended and security fee status updated.",
        "record": SecurityDepositRecordSerializer(record).data,
        "details": {
            "deducted_amount": float(deduct_amt),
            "remaining_balance": float(record.balance_amount),
            "license_suspended": license_suspended,
            "license_id": license_id_str,
            "application_updated": app_updated,
        }
    }, status=status.HTTP_200_OK)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def refund_security_deposit(request, pk):
    """
    Refund / return security deposit to licensee.
    """
    from .serializers import SecurityDepositRecordSerializer

    try:
        record = SecurityDepositRecord.objects.select_for_update().get(pk=pk)
    except SecurityDepositRecord.DoesNotExist:
        return Response({"detail": "Security deposit record not found."}, status=status.HTTP_404_NOT_FOUND)

    raw_refund_amount = request.data.get("refund_amount") or request.data.get("amount")
    remarks = str(request.data.get("remarks") or request.data.get("reason") or "Security deposit refunded").strip()

    current_balance = Decimal(str(record.balance_amount or 0)).quantize(Decimal("0.01"))
    if current_balance <= Decimal("0.00"):
        return Response({"detail": "No balance remaining to refund."}, status=status.HTTP_400_BAD_REQUEST)

    if raw_refund_amount is not None and str(raw_refund_amount).strip():
        try:
            refund_amt = Decimal(str(raw_refund_amount)).quantize(Decimal("0.01"))
            if refund_amt <= Decimal("0.00"):
                return Response({"detail": "Refund amount must be greater than zero."}, status=status.HTTP_400_BAD_REQUEST)
            if refund_amt > current_balance:
                return Response(
                    {"detail": f"Refund amount (₹{refund_amt}) cannot exceed remaining balance (₹{current_balance})."},
                    status=status.HTTP_400_BAD_REQUEST
                )
        except Exception as exc:
            return Response({"detail": f"Invalid refund amount: {exc}"}, status=status.HTTP_400_BAD_REQUEST)
    else:
        refund_amt = current_balance

    with transaction.atomic():
        old_refunded = Decimal(str(record.refunded_amount or 0)).quantize(Decimal("0.01"))
        record.refunded_amount = old_refunded + refund_amt
        record.balance_amount = max(Decimal("0.00"), record.amount - record.refunded_amount)
        if record.balance_amount == Decimal("0.00"):
            record.status = "REFUNDED"
        else:
            record.status = "PARTIALLY_REFUNDED"
        record.to_date = timezone.now().date()
        admin_info = f"Refunded ₹{refund_amt} on {timezone.now().strftime('%d-%m-%Y %H:%M')}. Remarks: {remarks}"
        if record.remarks:
            record.remarks = f"{record.remarks}\n[{admin_info}]"
        else:
            record.remarks = admin_info
        record.save()

    return Response({
        "status": "success",
        "message": f"Successfully refunded ₹{refund_amt} to licensee.",
        "record": SecurityDepositRecordSerializer(record).data,
    }, status=status.HTTP_200_OK)

