from decimal import Decimal
import logging

from django.db import transaction
from django.utils import timezone

from .models import PaymentHeadOfAccount, WalletBalance

logger = logging.getLogger(__name__)


# Runtime classification requested by business:
# value comes from the selected license subcategory at application time.
# 2 -> distillery, 1 -> brewery.
SUBCATEGORY_TO_MODULE_TYPE = {
    1: "brewery",
    2: "distillery",
}

COMMON_EDUCATION_CESS_HOA = "0045-00-112-45-03"
COMMON_HOLOGRAM_HOA = "0039-00-800-45-01"
COMMON_SECURITY_DEPOSIT_HOA = "0088-00-888-88-88"
COMMON_LICENSE_FEE_HOA = "0099-00-999-99-99"


HOA_CANDIDATES = {
    "distillery": {
        "excise": ["0039-00-105-45-01"],
        "education_cess": [COMMON_EDUCATION_CESS_HOA],
        "hologram": [COMMON_HOLOGRAM_HOA],
        "security_deposit": [COMMON_SECURITY_DEPOSIT_HOA],
        "license_fee": [COMMON_LICENSE_FEE_HOA],
    },
    "brewery": {
        "excise": ["0038-00-102-45-00"],
        # Same HOA as distillery for these two wallets by business rule.
        "education_cess": [COMMON_EDUCATION_CESS_HOA],
        "hologram": [COMMON_HOLOGRAM_HOA],
        "security_deposit": [COMMON_SECURITY_DEPOSIT_HOA],
        "license_fee": [COMMON_LICENSE_FEE_HOA],
    },
    "other": {
        "security_deposit": [COMMON_SECURITY_DEPOSIT_HOA],
        "license_fee": [COMMON_LICENSE_FEE_HOA],
    },
}


WALLET_LABELS = {
    "excise": "Excise / Additional Wallet",
    "education_cess": "Education Cess Wallet",
    "hologram": "Hologram",
    "security_deposit": "Security Deposit Wallet",
    "license_fee": "License Fee Wallet",
}


def _resolve_module_type(license_obj) -> str:
    sub_category_id = getattr(license_obj, "license_sub_category_id", None)
    # Prefer text-based inference first to avoid relying on environment-specific PKs.
    sub_category = getattr(license_obj, "license_sub_category", None)
    sub_desc = str(getattr(sub_category, "description", "") or "").strip().lower()
    if "distill" in sub_desc:
        return "distillery"
    if "brew" in sub_desc or "beer" in sub_desc:
        return "brewery"
    if sub_desc:
        return "other"

    module_type = SUBCATEGORY_TO_MODULE_TYPE.get(sub_category_id)
    if module_type:
        return module_type

    source = getattr(license_obj, "source_application", None)
    license_type = getattr(source, "license_type", None) if source is not None else None
    type_name = str(getattr(license_type, "license_type", "") or "").strip().lower()
    if "distill" in type_name:
        return "distillery"
    if "brew" in type_name or "beer" in type_name:
        return "brewery"
    if type_name:
        return "other"

    logger.warning(
        "Unknown license_sub_category_id=%s for license_id=%s. Falling back to distillery mapping.",
        sub_category_id,
        getattr(license_obj, "license_id", None),
    )
    return "other"


def _resolve_hoa_code(module_type: str, wallet_type: str) -> str:
    candidates = HOA_CANDIDATES.get(module_type, {}).get(wallet_type, [])
    if not candidates:
        raise ValueError(f"No HOA candidates configured for module_type={module_type}, wallet_type={wallet_type}")

    active_codes = set(
        PaymentHeadOfAccount.objects.filter(
            head_of_account__in=candidates,
            visible_status="Y",
        ).values_list("head_of_account", flat=True)
    )
    for code in candidates:
        if code in active_codes:
            return code

    existing_codes = set(
        PaymentHeadOfAccount.objects.filter(
            head_of_account__in=candidates,
        ).values_list("head_of_account", flat=True)
    )
    for code in candidates:
        if code in existing_codes:
            return code

    logger.warning(
        "None of the configured HOA candidates exist in master table for module_type=%s, wallet_type=%s. "
        "Using fallback candidate=%s",
        module_type,
        wallet_type,
        candidates[0],
    )
    return candidates[0]


def _build_person_name(license_obj) -> str:
    source = getattr(license_obj, "source_application", None)
    if source is not None:
        applicant_name = getattr(source, "applicant_name", None)
        if applicant_name:
            return str(applicant_name).strip()

        member_name = getattr(source, "member_name", None)
        if member_name:
            return str(member_name).strip()

        first_name = str(getattr(source, "firstName", "") or "").strip()
        middle_name = str(getattr(source, "middleName", "") or "").strip()
        last_name = str(getattr(source, "lastName", "") or "").strip()
        full_name = " ".join([part for part in [first_name, middle_name, last_name] if part]).strip()
        if full_name:
            return full_name

    applicant = getattr(license_obj, "applicant", None)
    if applicant is not None:
        full_name = " ".join(
            [
                str(getattr(applicant, "first_name", "") or "").strip(),
                str(getattr(applicant, "middle_name", "") or "").strip(),
                str(getattr(applicant, "last_name", "") or "").strip(),
            ]
        ).strip()
        if full_name:
            return full_name
        if getattr(applicant, "username", None):
            return str(applicant.username).strip()

    return ""


def _build_manufacturing_unit_name(license_obj) -> str:
    source = getattr(license_obj, "source_application", None)
    if source is not None:
        establishment_name = getattr(source, "establishment_name", None)
        if establishment_name:
            return str(establishment_name).strip()

        company_name = getattr(source, "company_name", None)
        if company_name:
            return str(company_name).strip()

        applicant_name = getattr(source, "applicant_name", None)
        if applicant_name:
            return str(applicant_name).strip()

        member_name = getattr(source, "member_name", None)
        if member_name:
            return str(member_name).strip()

        first_name = str(getattr(source, "firstName", "") or "").strip()
        middle_name = str(getattr(source, "middleName", "") or "").strip()
        last_name = str(getattr(source, "lastName", "") or "").strip()
        full_name = " ".join([part for part in [first_name, middle_name, last_name] if part]).strip()
        if full_name:
            return full_name

    applicant = getattr(license_obj, "applicant", None)
    if applicant is not None:
        full_name = " ".join(
            [
                str(getattr(applicant, "first_name", "") or "").strip(),
                str(getattr(applicant, "middle_name", "") or "").strip(),
                str(getattr(applicant, "last_name", "") or "").strip(),
            ]
        ).strip()
        if full_name:
            return full_name
        if getattr(applicant, "username", None):
            return str(applicant.username).strip()

    return ""


def _build_user_id(license_obj) -> str:
    applicant = getattr(license_obj, "applicant", None)
    if applicant is None:
        return ""

    username = getattr(applicant, "username", None)
    if username:
        return str(username).strip()

    return str(getattr(applicant, "pk", "") or "").strip()


def initialize_wallet_balances_for_license(license_obj) -> None:
    if license_obj is None:
        return

    licensee_id = str(getattr(license_obj, "license_id", "") or "").strip()
    if not licensee_id:
        logger.warning("Skipping wallet initialization: missing license_id")
        return

    module_type = _resolve_module_type(license_obj)
    person_name = _build_person_name(license_obj)
    manufacturing_unit = _build_manufacturing_unit_name(license_obj)
    user_id = _build_user_id(license_obj)
    now = timezone.now()

    if module_type in {"distillery", "brewery"}:
        wallet_types = ["excise", "education_cess", "hologram", "security_deposit", "license_fee"]
    else:
        wallet_types = ["security_deposit", "license_fee"]

    with transaction.atomic():
        for wallet_type in wallet_types:
            hoa_code = _resolve_hoa_code(module_type, wallet_type)
            label = WALLET_LABELS[wallet_type]

            # Idempotent behavior: if wallet rows already exist for this license + wallet type,
            # keep monetary values and only refresh metadata + HOA.
            existing_qs = WalletBalance.objects.filter(
                licensee_id=licensee_id,
                wallet_type=wallet_type,
            )
            if existing_qs.exists():
                existing_qs.update(
                    licensee_name=person_name,
                    manufacturing_unit=manufacturing_unit,
                    user_id=user_id,
                    module_type=module_type,
                    head_of_account=hoa_code,
                    last_updated_at=now,
                )
                continue

            WalletBalance.objects.create(
                licensee_id=licensee_id,
                licensee_name=person_name,
                manufacturing_unit=manufacturing_unit,
                user_id=user_id,
                module_type=module_type,
                wallet_type=wallet_type,
                head_of_account=hoa_code,
                opening_balance=Decimal("0.00"),
                total_credit=Decimal("0.00"),
                total_debit=Decimal("0.00"),
                current_balance=Decimal("0.00"),
                last_updated_at=now,
                created_at=now,
            )

            logger.info(
                "Initialized wallet balance: licensee_id=%s module_type=%s wallet_type=%s hoa=%s label=%s",
                licensee_id,
                module_type,
                wallet_type,
                hoa_code,
                label,
            )
