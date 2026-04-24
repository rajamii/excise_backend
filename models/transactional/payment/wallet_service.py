from __future__ import annotations

from decimal import Decimal
import logging

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .models import WalletBalance, WalletTransaction, _resolve_module_type_from_license_id, _resolve_wallet_row_licensee_id

logger = logging.getLogger(__name__)


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
) -> tuple[WalletTransaction | None, WalletBalance | None, bool]:
    """
    Credits wallet_balances + inserts wallet_transactions (idempotent).

    Returns: (wallet_transaction, wallet_balance, already_processed)
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

    existing = (
        WalletTransaction.objects.filter(
            transaction_id=txn,
            transaction_type__iexact=transaction_type,
            entry_type__iexact=entry_type,
        )
        .order_by("-wallet_transaction_id")
        .first()
    )
    if existing:
        return existing, None, True

    wallet_filter = Q(licensee_id__iexact=resolved_licensee_id)
    if str(user_id or "").strip():
        wallet_filter |= Q(user_id__iexact=str(user_id).strip())

    with transaction.atomic():
        wallet = (
            WalletBalance.objects.select_for_update()
            .filter(wallet_filter, wallet_type__iexact=wtype, head_of_account=hoa)
            .order_by("wallet_balance_id")
            .first()
        )
        if not wallet:
            template = (
                WalletBalance.objects.select_for_update()
                .filter(wallet_filter)
                .order_by("wallet_balance_id")
                .first()
            )
            wallet = WalletBalance.objects.create(
                licensee_id=resolved_licensee_id,
                licensee_name=str(licensee_name or getattr(template, "licensee_name", "") or "").strip(),
                manufacturing_unit=str(getattr(template, "manufacturing_unit", "") or "").strip() if template else "",
                user_id=str(user_id or getattr(template, "user_id", "") or "").strip(),
                module_type=str(getattr(template, "module_type", "") or "").strip() if template else resolved_module_type,
                wallet_type=wtype,
                head_of_account=hoa,
                opening_balance=Decimal("0.00"),
                total_credit=Decimal("0.00"),
                total_debit=Decimal("0.00"),
                current_balance=Decimal("0.00"),
                last_updated_at=now_ts,
                created_at=now_ts,
            )

        before = Decimal(str(wallet.current_balance or 0)).quantize(Decimal("0.01"))
        after = (before + amt).quantize(Decimal("0.01"))

        wallet.current_balance = after
        wallet.total_credit = (Decimal(str(wallet.total_credit or 0)) + amt).quantize(Decimal("0.01"))
        wallet.last_updated_at = now_ts
        wallet.save(update_fields=["current_balance", "total_credit", "last_updated_at"])

        created = WalletTransaction.objects.create(
            wallet_balance=wallet,
            transaction_id=txn,
            licensee_id=str(wallet.licensee_id or resolved_licensee_id).strip(),
            licensee_name=str(wallet.licensee_name or licensee_name or "").strip() or None,
            user_id=str(user_id or getattr(wallet, "user_id", "") or "").strip() or None,
            module_type=str(wallet.module_type or resolved_module_type).strip(),
            wallet_type=str(wallet.wallet_type or wtype).strip(),
            head_of_account=str(wallet.head_of_account or hoa).strip(),
            entry_type=str(entry_type or "CR").strip(),
            transaction_type=str(transaction_type or "recharge").strip(),
            amount=amt,
            balance_before=before,
            balance_after=after,
            reference_no=txn,
            source_module=str(source_module or "billdesk").strip(),
            payment_status=str(payment_status or "success").strip(),
            remarks=str(remarks or "").strip() or None,
            created_at=now_ts,
        )

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
    """
    Inserts a row in wallet_transactions without changing wallet balance.

    Useful for logging failed/aborted payment attempts so they show up in wallet history.
    Returns: (wallet_transaction, wallet_balance, already_processed)
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

    resolved_licensee_id = _resolve_wallet_row_licensee_id(raw_licensee, str(user_id or "").strip()) or raw_licensee
    resolved_module_type = _resolve_module_type_from_license_id(resolved_licensee_id, fallback="other") or "other"
    now_ts = timezone.now()

    existing = (
        WalletTransaction.objects.filter(
            transaction_id=txn,
            transaction_type__iexact=str(transaction_type or "recharge").strip(),
            entry_type__iexact=str(entry_type or "CR").strip(),
        )
        .order_by("-wallet_transaction_id")
        .first()
    )
    if existing:
        return existing, None, True

    wallet_filter = Q(licensee_id__iexact=resolved_licensee_id)
    if str(user_id or "").strip():
        wallet_filter |= Q(user_id__iexact=str(user_id).strip())

    with transaction.atomic():
        wallet = (
            WalletBalance.objects.select_for_update()
            .filter(wallet_filter, wallet_type__iexact=wtype, head_of_account=hoa)
            .order_by("wallet_balance_id")
            .first()
        )
        if not wallet:
            template = (
                WalletBalance.objects.select_for_update()
                .filter(wallet_filter)
                .order_by("wallet_balance_id")
                .first()
            )
            wallet = WalletBalance.objects.create(
                licensee_id=resolved_licensee_id,
                licensee_name=str(licensee_name or getattr(template, "licensee_name", "") or "").strip(),
                manufacturing_unit=str(getattr(template, "manufacturing_unit", "") or "").strip() if template else "",
                user_id=str(user_id or getattr(template, "user_id", "") or "").strip(),
                module_type=str(getattr(template, "module_type", "") or "").strip() if template else resolved_module_type,
                wallet_type=wtype,
                head_of_account=hoa,
                opening_balance=Decimal("0.00"),
                total_credit=Decimal("0.00"),
                total_debit=Decimal("0.00"),
                current_balance=Decimal("0.00"),
                last_updated_at=now_ts,
                created_at=now_ts,
            )

        before = Decimal(str(wallet.current_balance or 0)).quantize(Decimal("0.01"))
        after = before

        created = WalletTransaction.objects.create(
            wallet_balance=wallet,
            transaction_id=txn,
            licensee_id=str(wallet.licensee_id or resolved_licensee_id).strip(),
            licensee_name=str(wallet.licensee_name or licensee_name or "").strip() or None,
            user_id=str(user_id or getattr(wallet, "user_id", "") or "").strip() or None,
            module_type=str(wallet.module_type or resolved_module_type).strip(),
            wallet_type=str(wallet.wallet_type or wtype).strip(),
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
