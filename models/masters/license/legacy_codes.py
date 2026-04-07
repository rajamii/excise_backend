from __future__ import annotations

from typing import Tuple

from models.masters.core.models import LicenseCategory, LicenseSubcategory


def _resolve_legacy_codes_from_master_ids(
    cat_code: int | None, scat_code: int | None
) -> tuple[int | None, int | None]:
    """
    Resolve legacy (old) license category/subcategory codes when `cat_code` and/or
    `scat_code` are master table PKs (LicenseCategory / LicenseSubcategory).

    If old codes are missing, fall back to the original inputs.
    """
    if cat_code is None and scat_code is None:
        return None, None

    legacy_cat: int | None = None
    legacy_scat: int | None = None

    # Prefer resolving from subcategory, because it can provide both legacy codes.
    if scat_code is not None:
        row = (
            LicenseSubcategory.objects.filter(pk=int(scat_code))
            .values("old_license_cat_code", "old_license_scat_code", "category_id")
            .first()
        )
        if row:
            if row.get("old_license_scat_code") is not None:
                legacy_scat = int(row["old_license_scat_code"])
            else:
                legacy_scat = int(scat_code)

            if row.get("old_license_cat_code") is not None:
                legacy_cat = int(row["old_license_cat_code"])
            else:
                # If cat_code wasn't provided, try resolving via FK category_id.
                if cat_code is None and row.get("category_id") is not None:
                    cat_code = int(row["category_id"])

    if legacy_scat is None and scat_code is not None:
        legacy_scat = int(scat_code)

    if legacy_cat is None and cat_code is not None:
        old_cat = (
            LicenseCategory.objects.filter(pk=int(cat_code))
            .values_list("old_license_cat_code", flat=True)
            .first()
        )
        legacy_cat = int(old_cat) if old_cat is not None else int(cat_code)

    return legacy_cat, legacy_scat


def resolve_codes_for_license_form(
    cat_code: int | None, scat_code: int | None
) -> Tuple[int | None, int | None]:
    """
    Terms & conditions and license titles are keyed by *legacy* codes
    (`licensee_cat_code`, `licensee_scat_code`) in:
    - master_license_form
    - master_license_form_terms

    Most transactional records store FK ids for:
    - masters_licensecategory (LicenseCategory.pk)
    - masters_licensesubcategory (LicenseSubcategory.pk)

    Strategy:
    - Treat inputs as master table PKs first (current production data model).
    - If they don't exist as PKs, fall back to treating inputs as already-legacy codes.

    This intentionally prefers the old-code mapping even when the numeric PKs happen
    to match existing legacy terms rows, because terms must be driven by legacy codes.
    """
    if cat_code is None or scat_code is None:
        return cat_code, scat_code

    c = int(cat_code)
    s = int(scat_code)

    # Prefer mapping from masters_* PKs to legacy codes.
    legacy_cat, legacy_scat = _resolve_legacy_codes_from_master_ids(c, s)

    # If neither master PK exists, treat inputs as already-legacy.
    if legacy_cat is None and legacy_scat is None:
        return c, s

    return legacy_cat if legacy_cat is not None else c, legacy_scat if legacy_scat is not None else s
