from __future__ import annotations

from django.contrib.contenttypes.models import ContentType

from models.masters.license.models import License


def _normalize_token(value) -> str:
    return "".join(ch for ch in str(value or "").lower() if ch.isalnum())


def _expand_license_aliases(value: str) -> list[str]:
    normalized = str(value or "").strip()
    if not normalized:
        return []
    aliases = [normalized]
    if normalized.startswith("NLI/"):
        aliases.append(f"NA/{normalized[4:]}")
    elif normalized.startswith("NA/"):
        aliases.append(f"NLI/{normalized[3:]}")
    return aliases


def is_licensee_or_oic_user(user) -> bool:
    if not user:
        return False
    role_token = _normalize_token(getattr(getattr(user, "role", None), "name", ""))
    if role_token in {"licensee", "licencee"}:
        return True
    if (
        bool(getattr(user, "is_oic_managed", False))
        or hasattr(user, "oic_assignment")
        or role_token in {"officerincharge", "offcierincharge", "oic"}
    ):
        return True
    return False


def user_scoped_license_ids(user) -> set[str]:
    """
    Resolve license identifiers that should scope supply-chain master data for a user.

    Mirrors the license-id expansion used by transactional access control, but without
    requiring a workflow id.
    """
    scoped_values: set[str] = set()
    if not user:
        return scoped_values

    # Include mapped manufacturing units (licensee_id style identifiers).
    if hasattr(user, "manufacturing_units"):
        unit_licensee_ids = list(
            user.manufacturing_units.exclude(licensee_id__isnull=True)
            .exclude(licensee_id="")
            .values_list("licensee_id", flat=True)
        )
        for value in unit_licensee_ids:
            for alias in _expand_license_aliases(value):
                scoped_values.add(alias)

    # Include formal active license ids issued to the user.
    qs_by_applicant = License.objects.filter(applicant=user, is_active=True)

    # Compatibility: match license by source_object_id from user's new applications.
    try:
        from models.transactional.new_license_application.models import NewLicenseApplication

        new_app_ct = ContentType.objects.get_for_model(NewLicenseApplication)
        user_app_ids = NewLicenseApplication.objects.filter(applicant=user).values_list(
            "application_id", flat=True
        )
        qs_by_source_object = License.objects.filter(
            source_content_type=new_app_ct,
            source_object_id__in=user_app_ids,
            is_active=True,
        )
        license_qs = (qs_by_applicant | qs_by_source_object).distinct()
    except Exception:
        license_qs = qs_by_applicant

    license_ids = list(
        license_qs.exclude(license_id__isnull=True)
        .exclude(license_id="")
        .values_list("license_id", flat=True)
    )
    for value in license_ids:
        for alias in _expand_license_aliases(value):
            scoped_values.add(alias)

    return scoped_values

