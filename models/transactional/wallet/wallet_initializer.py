from functools import lru_cache
from decimal import Decimal
import logging
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from models.transactional.payment_gateway.models import PaymentModuleHoa
from .models import WalletBalance

logger = logging.getLogger(__name__)

def _looks_like_distillery(text: str) -> bool:
    t = str(text or "").strip().lower()
    return "distill" in t


def _looks_like_brewery(text: str) -> bool:
    t = str(text or "").strip().lower()
    return ("brew" in t) or ("beer" in t)

# COMMON_EDUCATION_CESS_HOA = "0045-00-112-45-03"
# COMMON_HOLOGRAM_HOA = "0039-00-800-45-01"
# COMMON_SECURITY_DEPOSIT_HOA = "non"
# COMMON_LICENSE_FEE_HOA = "0039-00-800-45-02"

# HOA_CANDIDATES = {
#     "distillery": {
#         "excise": ["0039-00-105-45-01"],
#         "education_cess": [COMMON_EDUCATION_CESS_HOA],
#         "hologram": [COMMON_HOLOGRAM_HOA],
#         "security_deposit": [COMMON_SECURITY_DEPOSIT_HOA],
#         "license_fee": [COMMON_LICENSE_FEE_HOA],
#     },
#     "brewery": {
#         "excise": ["0038-00-102-45-00"],
#         "education_cess": [COMMON_EDUCATION_CESS_HOA],
#         "hologram": [COMMON_HOLOGRAM_HOA],
#         "security_deposit": [COMMON_SECURITY_DEPOSIT_HOA],
#         "license_fee": [COMMON_LICENSE_FEE_HOA],
#     },
#     "other": {
#         "security_deposit": [COMMON_SECURITY_DEPOSIT_HOA],
#         "license_fee": [COMMON_LICENSE_FEE_HOA],
#     },
# }

# WALLET_LABELS = {
#     "excise": "Excise / Additional Wallet",
#     "education_cess": "Education Cess Wallet",
#     "hologram": "Hologram",
#     "security_deposit": "Security Deposit Wallet",
#     "license_fee": "License Fee Wallet",
# }


# @lru_cache(maxsize=1)
# def _hoa_master_table_exists() -> bool:
#     try:
#         return MasterHeadOfAccount._meta.db_table in set(connection.introspection.table_names())
#     except Exception:
#         return False


def _resolve_module_type(license_obj) -> str:
    sub_category_id = getattr(license_obj, "license_sub_category_id", None)
    sub_category = getattr(license_obj, "license_sub_category", None)
    sub_desc = str(getattr(sub_category, "description", "") or "").strip().lower()
    if _looks_like_distillery(sub_desc):
        return "distillery"
    if _looks_like_brewery(sub_desc):
        return "brewery"
    if sub_desc:
        return "other"

    # Fallback: Some deployments use stable numeric IDs (frontend also uses these).
    # Only apply when description is missing.
    try:
        sid = int(sub_category_id or 0)
    except Exception:
        sid = 0
    if sid == 2:
        return "distillery"
    if sid == 1:
        return "brewery"

    source_type = str(getattr(license_obj, "source_type", "") or "").strip().lower()
    if source_type in {"salesman_barman", "license_application"}:
        return "other"

    source = getattr(license_obj, "source_application", None)
    license_type = getattr(source, "license_type", None) if source is not None else None
    type_name = str(getattr(license_type, "license_type", "") or "").strip().lower()
    if _looks_like_distillery(type_name):
        return "distillery"
    if _looks_like_brewery(type_name):
        return "brewery"
    if type_name:
        return "other"

    logger.warning(
        "Unknown license_sub_category_id=%s for license_id=%s. Falling back to other mapping.",
        sub_category_id,
        getattr(license_obj, "license_id", None),
    )
    return "other"


def _resolve_hoa_code(module_type: str, wallet_type: str) -> str:
    """
    Strictly resolves the Head of Account from the database mapping table.
    No hardcoded fallbacks are allowed.
    """
    
    # 1. Query the mapping table directly using the Foreign Keys
    mapping = PaymentModuleHoa.objects.select_related('head_of_account').filter(
        module_code__module_desc__icontains=module_type,
        wallet_type__code__iexact=wallet_type, # Using the new Foreign Key to MasterWalletType
        is_active=True,                        # Using the new BooleanField
        head_of_account__visible_status=True    
    ).first()

    # 2. Return the Head of Account if a valid mapping exists
    if mapping and mapping.head_of_account:
        return mapping.head_of_account.head_of_account

    # 3. NO FALLBACK: Fail loudly if the DB doesn't have the mapping
    error_msg = (
        f"Configuration Error: No active Head of Account mapping found in the database "
        f"(sems_module_hoa) for module_type='{module_type}' and wallet_type='{wallet_type}'."
    )
    logger.critical(error_msg)
    
    raise ValidationError({
        "detail": error_msg,
        "code": "missing_hoa_mapping"
    })


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


def _resolve_primary_wallet_licensee_id(license_obj, *, fallback_licensee_id: str, user_id: str) -> str:
    """
    Wallets are shared per "primary holder" (applicant/user_id) across multiple license approvals.

    We still need a licensee_id value for wallet rows; treat an active NA/... for the applicant
    as the canonical one (supply-chain flows use NA/... heavily). If NA/... doesn't exist,
    fall back to the current issued license_id.
    """
    fallback = str(fallback_licensee_id or "").strip()
    user_key = str(user_id or "").strip()

    applicant = getattr(license_obj, "applicant", None)
    if applicant is not None:
        try:
            from models.masters.license.models import License

            lic = (
                License.objects.filter(applicant=applicant, is_active=True)
                .filter(license_id__istartswith="NA/")
                .order_by("-issue_date", "-license_id")
                .first()
            )
            if lic and lic.license_id:
                return str(lic.license_id).strip()
        except Exception:
            pass

    if user_key:
        # If we already have any wallet rows for this user, keep their licensee_id as stable fallback.
        template = (
            WalletBalance.objects.filter(user_id__iexact=user_key)
            .exclude(licensee_id__isnull=True)
            .exclude(licensee_id__exact="")
            .order_by("wallet_balance_id")
            .first()
        )
        template_id = str(getattr(template, "licensee_id", "") or "").strip()
        if template_id:
            return template_id

    return fallback


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
    primary_licensee_id = _resolve_primary_wallet_licensee_id(
        license_obj, fallback_licensee_id=licensee_id, user_id=user_id
    )
    now = timezone.now()

    if module_type in {"distillery", "brewery"}:
        wallet_types = ["excise", "education_cess", "hologram", "security_deposit", "license_fee"]
    else:
        wallet_types = ["security_deposit", "license_fee"]

    with transaction.atomic():
        for wallet_type in wallet_types:
            hoa_code = _resolve_hoa_code(module_type, wallet_type)

            existing_qs = WalletBalance.objects.none()
            if user_id:
                existing_qs = WalletBalance.objects.filter(
                    user_id__iexact=user_id, 
                    wallet_type_id=wallet_type 
                )
            if not existing_qs.exists():
                existing_qs = WalletBalance.objects.filter(
                    Q(licensee_id=licensee_id) | Q(licensee_id=primary_licensee_id),
                    wallet_type_id=wallet_type,
                )
            if existing_qs.exists():
                updates = {
                    "licensee_id": primary_licensee_id or licensee_id,
                    "module_type": module_type or "other",
                    "head_of_account": hoa_code,
                    "last_updated_at": now,
                }
                if person_name:
                    updates["licensee_name"] = person_name
                if manufacturing_unit:
                    updates["manufacturing_unit"] = manufacturing_unit
                if user_id:
                    updates["user_id"] = user_id
                existing_qs.update(**updates)
                continue

            WalletBalance.objects.create(
                licensee_id=primary_licensee_id or licensee_id,
                licensee_name=person_name or "",
                manufacturing_unit=manufacturing_unit or "",
                user_id=user_id or None,
                module_type=module_type or "other",
                wallet_type_id=wallet_type,
                head_of_account=hoa_code,
                opening_balance=Decimal("0.00"),
                total_credit=Decimal("0.00"),
                total_debit=Decimal("0.00"),
                current_balance=Decimal("0.00"),
                last_updated_at=now,
                created_at=now,
            )

