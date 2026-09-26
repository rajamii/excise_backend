from __future__ import annotations
from decimal import Decimal
import logging
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from .models import (
    WalletBalance,
    WalletTransaction,
    SecurityDepositRecord,
    _resolve_module_type_from_license_id,
    _resolve_wallet_row_licensee_id,
)

logger = logging.getLogger(__name__)

def _is_pending_payment_status(value: str | None) -> bool:
    raw = str(value or "").strip().lower()
    return raw in {"p", "pending", "processing", "in_progress", "inprogress"}


def credit_wallet_balance(
    *,
    transaction_id: str,
    licensee_id: str,
    wallet_type: str,
    head_of_account: str,
    amount: Decimal,
    entry_type: str = "CR",
    transaction_type: str = "recharge",
    user_id: str = "",
    licensee_name: str = "",
    source_module: str = "billdesk",
    payment_status: str = "success",
    remarks: str = "",
    reference_no: str = "",
) -> tuple[WalletTransaction | None, WalletBalance | None, bool]:
    txn = str(transaction_id or "").strip()
    if not txn:
        raise ValueError("transaction_id is required")

    raw_licensee = str(licensee_id or "").strip()
    if not raw_licensee:
        raise ValueError("licensee_id is required")

    wtype = str(wallet_type or "").strip()
    if not wtype:
        raise ValueError("wallet_type is required")

    hoa = str(head_of_account or "").strip() or "non"

    amt = Decimal(str(amount or "0")).quantize(Decimal("0.01"))
    if amt <= 0:
        raise ValueError("amount must be greater than zero")

    resolved_licensee_id = _resolve_wallet_row_licensee_id(raw_licensee, str(user_id or "").strip()) or raw_licensee
    resolved_module_type = _resolve_module_type_from_license_id(resolved_licensee_id, fallback="other") or "other"
    now_ts = timezone.now()

    wallet_filter = Q(licensee_id__iexact=resolved_licensee_id)
    if str(user_id or "").strip():
        wallet_filter |= Q(user_id__iexact=str(user_id).strip())

    with transaction.atomic():
        existing = (
            WalletTransaction.objects.select_for_update()
            .filter(
                transaction_id=txn,
                transaction_type__iexact=transaction_type,
                entry_type__iexact=entry_type,
            )
            .order_by("-wallet_transaction_id")
            .first()
        )
        if existing and not _is_pending_payment_status(getattr(existing, "payment_status", "")):
            return existing, None, True

        matching_codes = [wtype]
        if wtype.lower() in ('excise', 'additional_excise', 'additional_ed'):
            matching_codes = ['excise', 'additional_excise', 'additional_ed']

        wallet = (
            WalletBalance.objects.select_for_update()
            .filter(wallet_filter, wallet_type__code__in=matching_codes)
            .order_by("wallet_balance_id")
            .first()
        )
        if not wallet:
            raise ValueError(
                f"Wallet not found for licensee_id={resolved_licensee_id}, wallet_type={wtype}. "
                "Wallet must be initialized at license approval before any payment can be credited."
            )
        # if not wallet:
        #     template = WalletBalance.objects.select_for_update().filter(wallet_filter).order_by("wallet_balance_id").first()
        #     wallet = WalletBalance.objects.create(
        #         licensee_id=resolved_licensee_id,
        #         licensee_name=str(licensee_name or getattr(template, "licensee_name", "") or "").strip(),
        #         manufacturing_unit=str(getattr(template, "manufacturing_unit", "") or "").strip() if template else "",
        #         user_id=str(user_id or getattr(template, "user_id", "") or "").strip(),
        #         module_type=str(getattr(template, "module_type", "") or "").strip() if template else resolved_module_type,
        #         wallet_type=wtype,
        #         head_of_account=hoa,
        #         opening_balance=Decimal("0.00"),
        #         total_credit=Decimal("0.00"),
        #         total_debit=Decimal("0.00"),
        #         current_balance=Decimal("0.00"),
        #         last_updated_at=now_ts,
        #         created_at=now_ts,
        #     )

        before = Decimal(str(wallet.current_balance or 0)).quantize(Decimal("0.01"))
        after = (before + amt).quantize(Decimal("0.01"))

        wallet.current_balance = after
        wallet.total_credit = (Decimal(str(wallet.total_credit or 0)) + amt).quantize(Decimal("0.01"))
        wallet.last_updated_at = now_ts
        wallet.save(update_fields=["current_balance", "total_credit", "last_updated_at"])

        if existing and _is_pending_payment_status(getattr(existing, "payment_status", "")):
            existing.wallet_balance = wallet
            existing.licensee_id = str(wallet.licensee_id or resolved_licensee_id).strip()
            existing.licensee_name = str(wallet.licensee_name or licensee_name or "").strip() or None
            existing.user_id = str(user_id or getattr(wallet, "user_id", "") or "").strip() or None
            existing.module_type = str(wallet.module_type or resolved_module_type).strip()
            existing.wallet_type_id = str(wtype).strip()
            existing.head_of_account = str(wallet.head_of_account or hoa).strip()
            existing.amount = amt
            existing.balance_before = before
            existing.balance_after = after
            existing.reference_no = str(reference_no or txn).strip()
            existing.source_module = str(source_module or "billdesk").strip()
            existing.payment_status = str(payment_status or "success").strip()
            existing.remarks = str(remarks or "").strip() or None
            existing.created_at = getattr(existing, "created_at", None) or now_ts
            existing.save()
            created = existing
        else:
            created = WalletTransaction.objects.create(
                wallet_balance=wallet,
                transaction_id=txn,
                licensee_id=str(wallet.licensee_id or resolved_licensee_id).strip(),
                licensee_name=str(wallet.licensee_name or licensee_name or "").strip() or None,
                user_id=str(user_id or getattr(wallet, "user_id", "") or "").strip() or None,
                module_type=str(wallet.module_type or resolved_module_type).strip(),
                wallet_type_id=str(wtype).strip(),
                head_of_account=str(wallet.head_of_account or hoa).strip(),
                entry_type=str(entry_type or "CR").strip(),
                transaction_type=str(transaction_type or "recharge").strip(),
                amount=amt,
                balance_before=before,
                balance_after=after,
                reference_no=str(reference_no or txn).strip(),
                source_module=str(source_module or "billdesk").strip(),
                payment_status=str(payment_status or "success").strip(),
                remarks=str(remarks or "").strip() or None,
                created_at=now_ts,
            )

        # ---------- Admin Audit Log ('admin_log') ----------
        try:
            from models.transactional.logs.services import log_admin_action
            from django.contrib.auth import get_user_model
            from django.db.models import Q
            User = get_user_model()
            actor_user = None
            if user_id:
                if str(user_id).isdigit():
                    actor_user = User.objects.filter(pk=int(user_id)).first()
                if not actor_user:
                    actor_user = User.objects.filter(username__iexact=str(user_id).strip()).first()
            if not actor_user and resolved_licensee_id:
                actor_user = User.objects.filter(username__iexact=resolved_licensee_id).first()

            wallet_label = str(getattr(getattr(wallet, 'wallet_type', None), 'name', None) or wtype).replace('_', ' ').title()
            
            recharge_remarks = (
                f"Recharged ₹{amt:,.2f} to {wallet_label} Wallet for Licensee '{resolved_licensee_id}'. "
                f"Previous Balance: ₹{before:,.2f} → New Balance: ₹{after:,.2f} (Txn: {txn})."
            )
            if remarks:
                recharge_remarks += f" ({remarks})"

            log_admin_action(
                action="WALLET_RECHARGE",
                user=actor_user,
                module_name="Wallet Management",
                application_id=str(wallet.licensee_id or resolved_licensee_id),
                from_stage=f"₹{before:,.2f}",
                to_stage=f"₹{after:,.2f}",
                status="SUCCESS",
                remarks=recharge_remarks,
                metadata={
                    "wallet_id": getattr(wallet, 'pk', None),
                    "wallet_type": str(getattr(getattr(wallet, 'wallet_type', None), 'code', None) or wtype),
                    "wallet_label": wallet_label,
                    "licensee_id": str(wallet.licensee_id or resolved_licensee_id),
                    "licensee_name": str(wallet.licensee_name or licensee_name or ""),
                    "amount": str(amt),
                    "balance_before": str(before),
                    "balance_after": str(after),
                    "head_of_account": str(wallet.head_of_account or hoa),
                    "transaction_id": txn,
                    "reference_no": str(reference_no or txn),
                    "entry_type": "CR",
                    "source_module": str(source_module or "billdesk"),
                }
            )
        except Exception as log_exc:
            logger.warning("Failed to record admin_log for wallet recharge: %s", log_exc)

    return created, wallet, False


def record_wallet_transaction(
    *,
    transaction_id: str,
    licensee_id: str,
    wallet_type: str,
    head_of_account: str,
    amount: Decimal | str | int | float = Decimal("0.00"),
    entry_type: str = "CR",
    transaction_type: str = "recharge",
    user_id: str = "",
    licensee_name: str = "",
    source_module: str = "billdesk",
    payment_status: str = "failed",
    remarks: str = "",
) -> tuple[WalletTransaction | None, WalletBalance | None, bool]:
    txn = str(transaction_id or "").strip()
    if not txn:
        raise ValueError("transaction_id is required")

    raw_licensee = str(licensee_id or "").strip()
    if not raw_licensee:
        raise ValueError("licensee_id is required")

    wtype = str(wallet_type or "").strip()
    if not wtype:
        raise ValueError("wallet_type is required")

    hoa = str(head_of_account or "").strip() or "non"
    amt = Decimal(str(amount or "0")).quantize(Decimal("0.01"))

    resolved_licensee_id = _resolve_wallet_row_licensee_id(raw_licensee, str(user_id or "").strip()) or raw_licensee
    resolved_module_type = _resolve_module_type_from_license_id(resolved_licensee_id, fallback="other") or "other"
    now_ts = timezone.now()

    wallet_filter = Q(licensee_id__iexact=resolved_licensee_id)
    if str(user_id or "").strip():
        wallet_filter |= Q(user_id__iexact=str(user_id).strip())

    with transaction.atomic():
        existing = (
            WalletTransaction.objects.select_for_update()
            .filter(
                transaction_id=txn,
                transaction_type__iexact=str(transaction_type or "recharge").strip(),
                entry_type__iexact=str(entry_type or "CR").strip(),
            )
            .order_by("-wallet_transaction_id")
            .first()
        )
        if existing and _is_pending_payment_status(getattr(existing, "payment_status", "")) and str(payment_status or "").strip():
            existing.payment_status = str(payment_status).strip()
            if str(remarks or "").strip():
                existing.remarks = str(remarks).strip()
            existing.save(update_fields=["payment_status", "remarks"])
            return existing, None, False
        if existing:
            return existing, None, True

        wallet = (
            WalletBalance.objects.select_for_update()
            .filter(wallet_filter, wallet_type__code__iexact=wtype, head_of_account=hoa)
            .order_by("wallet_balance_id")
            .first()
        )
        # COMMENTED OUT: Wallet should already exist (created at commissioner approval stage).
        # Creating a new dummy WalletBalance row here during payment recording was causing a
        # duplicate/ghost row in wallet_balances. Raise an error if wallet is missing instead.
        if not wallet:
            raise ValueError(
                f"Wallet not found for licensee_id={resolved_licensee_id}, wallet_type={wtype}, "
                f"head_of_account={hoa}. Wallet must be initialized at license approval before recording transactions."
            )
        # if not wallet:
        #     template = WalletBalance.objects.select_for_update().filter(wallet_filter).order_by("wallet_balance_id").first()
        #     wallet = WalletBalance.objects.create(
        #         licensee_id=resolved_licensee_id,
        #         licensee_name=str(licensee_name or getattr(template, "licensee_name", "") or "").strip(),
        #         manufacturing_unit=str(getattr(template, "manufacturing_unit", "") or "").strip() if template else "",
        #         user_id=str(user_id or getattr(template, "user_id", "") or "").strip(),
        #         module_type=str(getattr(template, "module_type", "") or "").strip() if template else resolved_module_type,
        #         wallet_type=wtype,
        #         head_of_account=hoa,
        #         opening_balance=Decimal("0.00"),
        #         total_credit=Decimal("0.00"),
        #         total_debit=Decimal("0.00"),
        #         current_balance=Decimal("0.00"),
        #         last_updated_at=now_ts,
        #         created_at=now_ts,
        #     )

        before = Decimal(str(wallet.current_balance or 0)).quantize(Decimal("0.01"))
        after = before

        created = WalletTransaction.objects.create(
            wallet_balance=wallet,
            transaction_id=txn,
            licensee_id=str(wallet.licensee_id or resolved_licensee_id).strip(),
            licensee_name=str(wallet.licensee_name or licensee_name or "").strip() or None,
            user_id=str(user_id or getattr(wallet, "user_id", "") or "").strip() or None,
            module_type=str(wallet.module_type or resolved_module_type).strip(),
            wallet_type_id=str(getattr(wallet, "wallet_type_id", None) or wtype).strip(),
            head_of_account=str(wallet.head_of_account or hoa).strip(),
            entry_type=str(entry_type or "CR").strip(),
            transaction_type=str(transaction_type or "recharge").strip(),
            amount=amt,
            balance_before=before,
            balance_after=after,
            reference_no=txn,
            source_module=str(source_module or "billdesk").strip(),
            payment_status=str(payment_status or "failed").strip(),
            remarks=str(remarks or "").strip() or None,
            created_at=now_ts,
        )

    return created, wallet, False


def debit_wallet_balance(
    *,
    transaction_id: str,
    licensee_id: str,
    wallet_type: str,
    head_of_account: str,
    amount: Decimal,
    user_id: str = "",
    licensee_name: str = "",
    source_module: str = "wallet_payment",
    payment_status: str = "success",
    remarks: str = "",
    transaction_type: str = "payment",
    reference_no: str = "",
) -> tuple[WalletTransaction | None, WalletBalance | None, bool]:
    """
    Debit a wallet balance and create a DR WalletTransaction.

    Returns: (wallet_txn, wallet_balance, already_processed)
    """
    txn = str(transaction_id or "").strip()
    if not txn:
        raise ValueError("transaction_id is required")

    raw_licensee = str(licensee_id or "").strip()
    if not raw_licensee:
        raise ValueError("licensee_id is required")

    wtype = str(wallet_type or "").strip()
    if not wtype:
        raise ValueError("wallet_type is required")

    hoa = str(head_of_account or "").strip() or "non"

    amt = Decimal(str(amount or "0")).quantize(Decimal("0.01"))
    if amt <= 0:
        raise ValueError("amount must be greater than zero")

    resolved_licensee_id = _resolve_wallet_row_licensee_id(raw_licensee, str(user_id or "").strip()) or raw_licensee
    resolved_module_type = _resolve_module_type_from_license_id(resolved_licensee_id, fallback="other") or "other"
    now_ts = timezone.now()

    wallet_filter = Q(licensee_id__iexact=resolved_licensee_id)
    if str(user_id or "").strip():
        wallet_filter |= Q(user_id__iexact=str(user_id).strip())

    with transaction.atomic():
        existing = (
            WalletTransaction.objects.select_for_update()
            .filter(
                transaction_id=txn,
                transaction_type__iexact=str(transaction_type or "payment").strip(),
                entry_type__iexact="DR",
            )
            .order_by("-wallet_transaction_id")
            .first()
        )
        if existing and not _is_pending_payment_status(getattr(existing, "payment_status", "")):
            return existing, None, True

        matching_codes = [wtype]
        if wtype.lower() in ('excise', 'additional_excise', 'additional_ed'):
            matching_codes = ['excise', 'additional_excise', 'additional_ed']

        wallet = (
            WalletBalance.objects.select_for_update()
            .filter(wallet_filter, wallet_type__code__in=matching_codes)
            .order_by("wallet_balance_id")
            .first()
        )
        if not wallet:
            raise ValueError(f"Wallet not found for wallet_type={wtype}, head_of_account={hoa}")

        before = Decimal(str(wallet.current_balance or 0)).quantize(Decimal("0.01"))
        if before < amt:
            raise ValueError("Insufficient wallet balance")

        after = (before - amt).quantize(Decimal("0.01"))
        wallet.current_balance = after
        wallet.total_debit = (Decimal(str(wallet.total_debit or 0)) + amt).quantize(Decimal("0.01"))
        wallet.last_updated_at = now_ts
        wallet.save(update_fields=["current_balance", "total_debit", "last_updated_at"])

        created = WalletTransaction.objects.create(
            wallet_balance=wallet,
            transaction_id=txn,
            licensee_id=str(wallet.licensee_id or resolved_licensee_id).strip(),
            licensee_name=str(wallet.licensee_name or licensee_name or "").strip() or None,
            user_id=str(user_id or getattr(wallet, "user_id", "") or "").strip() or None,
            module_type=str(wallet.module_type or resolved_module_type).strip(),
            wallet_type_id=str(wtype).strip(),
            head_of_account=str(wallet.head_of_account or hoa).strip(),
            entry_type="DR",
            transaction_type=str(transaction_type or "payment").strip(),
            amount=amt,
            balance_before=before,
            balance_after=after,
            reference_no=str(reference_no or txn).strip(),
            source_module=str(source_module or "wallet_payment").strip(),
            payment_status=str(payment_status or "success").strip(),
            remarks=str(remarks or "").strip() or None,
            created_at=now_ts,
        )

        # ---------- Admin Audit Log ('admin_log') ----------
        try:
            from models.transactional.logs.services import log_admin_action
            from django.contrib.auth import get_user_model
            from django.db.models import Q
            User = get_user_model()
            actor_user = None
            if user_id:
                if str(user_id).isdigit():
                    actor_user = User.objects.filter(pk=int(user_id)).first()
                if not actor_user:
                    actor_user = User.objects.filter(username__iexact=str(user_id).strip()).first()
            if not actor_user and resolved_licensee_id:
                actor_user = User.objects.filter(username__iexact=resolved_licensee_id).first()

            wallet_label = str(getattr(getattr(wallet, 'wallet_type', None), 'name', None) or wtype).replace('_', ' ').title()
            
            debit_remarks = (
                f"Debited ₹{amt:,.2f} from {wallet_label} Wallet for Licensee '{resolved_licensee_id}'. "
                f"Previous Balance: ₹{before:,.2f} → New Balance: ₹{after:,.2f}."
            )
            if remarks:
                debit_remarks += f" Reason: {remarks}."

            log_admin_action(
                action="WALLET_DEBIT",
                user=actor_user,
                module_name="Wallet Management",
                application_id=str(wallet.licensee_id or resolved_licensee_id),
                from_stage=f"₹{before:,.2f}",
                to_stage=f"₹{after:,.2f}",
                status="SUCCESS",
                remarks=debit_remarks,
                metadata={
                    "wallet_id": getattr(wallet, 'pk', None),
                    "wallet_type": str(getattr(getattr(wallet, 'wallet_type', None), 'code', None) or wtype),
                    "wallet_label": wallet_label,
                    "licensee_id": str(wallet.licensee_id or resolved_licensee_id),
                    "licensee_name": str(wallet.licensee_name or licensee_name or ""),
                    "amount": str(amt),
                    "balance_before": str(before),
                    "balance_after": str(after),
                    "head_of_account": str(wallet.head_of_account or hoa),
                    "transaction_id": txn,
                    "reference_no": str(reference_no or txn),
                    "entry_type": "DR",
                    "purpose": str(remarks or transaction_type),
                    "source_module": str(source_module or "wallet_payment"),
                }
            )
        except Exception as log_exc:
            logger.warning("Failed to record admin_log for wallet debit: %s", log_exc)

    return created, wallet, False


def create_or_update_security_deposit_record(
    *,
    application=None,
    application_id: str | None = None,
    user=None,
    user_id: str | int | None = None,
    username: str | None = None,
    applicant_name: str | None = None,
    establishment_name: str | None = None,
    license_id: str | None = None,
    amount: Decimal | float | int | str | None = None,
    refunded_amount: Decimal | float | int | str | None = None,
    transaction_id: str | None = None,
    reference_no: str | None = None,
    payment_date=None,
    from_date=None,
    to_date=None,
    status: str | None = None,
    remarks: str | None = None,
) -> SecurityDepositRecord | None:
    """
    Creates or updates a record in SecurityDepositRecord table when a user pays
    the security deposit for their license application.
    """
    try:
        app_obj = application
        app_id = str(application_id or getattr(application, "application_id", "") or "").strip()

        if not app_obj and app_id:
            try:
                from models.transactional.new_license_application.models import NewLicenseApplication
                app_obj = (
                    NewLicenseApplication.objects.select_related("applicant")
                    .filter(application_id__iexact=app_id)
                    .first()
                )
            except Exception:
                app_obj = None

        if app_obj and not app_id:
            app_id = str(getattr(app_obj, "application_id", "") or "").strip()

        # User resolution
        user_obj = user
        if not user_obj and app_obj and getattr(app_obj, "applicant", None):
            user_obj = app_obj.applicant

        resolved_user_id = str(user_id or (getattr(user_obj, "id", None) if user_obj else "") or "").strip()
        resolved_username = str(username or (getattr(user_obj, "username", None) if user_obj else "") or "").strip()

        # Applicant name
        resolved_applicant_name = str(
            applicant_name
            or getattr(app_obj, "applicant_name", None)
            or (getattr(user_obj, "get_full_name", lambda: "")() if user_obj else "")
            or resolved_username
        ).strip()

        # Establishment name
        resolved_est_name = str(
            establishment_name
            or getattr(app_obj, "establishment_name", None)
            or ""
        ).strip()

        # License ID resolution
        resolved_license_id = str(license_id or "").strip()
        if not resolved_license_id and app_obj:
            try:
                from models.masters.license.models import License
                from django.contrib.contenttypes.models import ContentType
                new_app_ct = ContentType.objects.get_for_model(app_obj.__class__)
                lic = (
                    License.objects.filter(
                        source_type="new_license_application",
                        source_content_type=new_app_ct,
                        source_object_id=str(app_obj.pk),
                    )
                    .order_by("-issue_date", "-license_id")
                    .first()
                )
                if lic and lic.license_id:
                    resolved_license_id = str(lic.license_id).strip()
            except Exception:
                pass

        # Amount resolution
        resolved_amount = None
        if amount is not None:
            try:
                resolved_amount = Decimal(str(amount)).quantize(Decimal("0.01"))
            except Exception:
                resolved_amount = None

        if resolved_amount is None and app_obj:
            try:
                from models.masters.core.models import LicenseFee
                fee = None
                if getattr(app_obj, "licensee_fee_id", None):
                    fee = LicenseFee.objects.filter(id=app_obj.licensee_fee_id).first()
                if not fee:
                    fee = (
                        LicenseFee.objects.filter(
                            license_category=app_obj.license_category,
                            license_subcategory=app_obj.license_sub_category,
                        )
                        .order_by("-id")
                        .first()
                    )
                if fee and getattr(fee, "security_amount", None) is not None:
                    resolved_amount = Decimal(str(fee.security_amount)).quantize(Decimal("0.01"))
            except Exception:
                pass

        txn_id = str(transaction_id or "").strip()
        ref_no = str(reference_no or app_id or txn_id).strip()
        pay_date = payment_date or timezone.now()
        rem = str(remarks or f"Security deposit paid for {app_id}").strip()

        with transaction.atomic():
            record = None
            if app_id:
                record = SecurityDepositRecord.objects.select_for_update().filter(application_id__iexact=app_id).first()
            if not record and txn_id:
                record = SecurityDepositRecord.objects.select_for_update().filter(transaction_id__iexact=txn_id).first()

            if not record:
                record = SecurityDepositRecord(
                    application_id=app_id,
                    transaction_id=txn_id,
                )
                if resolved_amount is not None and resolved_amount > Decimal("0.00"):
                    record.amount = resolved_amount
                elif amount is not None:
                    record.amount = Decimal(str(amount)).quantize(Decimal("0.01"))
                else:
                    record.amount = Decimal("5000.00")
            else:
                if amount is not None and resolved_amount is not None:
                    record.amount = resolved_amount
                elif (not record.amount or record.amount <= Decimal("0.00")) and resolved_amount is not None:
                    record.amount = resolved_amount

            if user_obj and getattr(user_obj, "is_authenticated", True):
                try:
                    record.user = user_obj
                except Exception:
                    pass
            if resolved_user_id:
                record.applicant_user_id = resolved_user_id
            if resolved_username:
                record.username = resolved_username
            if resolved_applicant_name:
                record.applicant_name = resolved_applicant_name
            if resolved_est_name:
                record.establishment_name = resolved_est_name
            if resolved_license_id:
                record.license_id = resolved_license_id
            if app_id:
                record.application_id = app_id
            if ref_no:
                record.reference_no = ref_no
            if txn_id:
                record.transaction_id = txn_id
            if resolved_amount is not None:
                record.amount = resolved_amount
            if refunded_amount is not None:
                try:
                    record.refunded_amount = Decimal(str(refunded_amount)).quantize(Decimal("0.01"))
                except Exception:
                    pass
            if status:
                record.status = status
            if pay_date:
                record.payment_date = pay_date
            if from_date:
                record.from_date = from_date
            elif not record.from_date and pay_date:
                record.from_date = pay_date.date() if hasattr(pay_date, "date") else pay_date
            record.save()

        # ---------- Admin Audit Log ('admin_log') ----------
        try:
            from models.transactional.logs.services import log_admin_action
            target_id = record.application_id or record.license_id or f"SD-{record.pk}"
            paid_amount = record.amount or resolved_amount or Decimal("0.00")
            log_admin_action(
                action="PAY_SECURITY_DEPOSIT",
                user=record.user or user_obj,
                module_name="Security Deposit Master",
                application_id=target_id,
                status="SUCCESS",
                remarks=f"Security Deposit of ₹{paid_amount:,.2f} recorded/paid for Application/License '{target_id}' (Licensee: {record.applicant_name or resolved_applicant_name}, Txn: {record.transaction_id or txn_id}).",
                metadata={
                    "security_deposit_record_id": record.pk,
                    "application_id": record.application_id or "",
                    "license_id": record.license_id or "",
                    "amount": str(paid_amount),
                    "balance_amount": str(record.balance_amount or paid_amount),
                    "transaction_id": record.transaction_id or txn_id,
                    "reference_no": record.reference_no or ref_no,
                    "licensee_name": record.applicant_name or resolved_applicant_name,
                    "establishment_name": record.establishment_name or resolved_est_name,
                }
            )
        except Exception as log_exc:
            logger.warning("Failed to record admin_log for security deposit payment: %s", log_exc)

        return record
    except Exception as exc:
        logger.error("Failed to create/update SecurityDepositRecord: %s", exc, exc_info=True)
        return None


