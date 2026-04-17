from django.test import TestCase

from models.masters.core.models import LicenseCategory, LicenseSubcategory
from models.masters.license.legacy_codes import resolve_codes_for_license_form
from models.masters.license.master_license_form import MasterLicenseForm
from models.masters.license.master_license_form_terms import MasterLicenseFormTerms


class LegacyLicenseCodeResolverTests(TestCase):
    def test_resolves_legacy_codes_from_master_ids(self):
        # Force a master PK that can collide with a legacy code to ensure we always map via old codes.
        cat = LicenseCategory.objects.create(
            id=16,
            license_category="Restaurant - cum - Bar Shop",
            old_license_cat_code=5,
        )
        scat = LicenseSubcategory.objects.create(
            description="Foreign Liquor Bar Shop",
            category=cat,
            old_license_cat_code=5,
            old_license_scat_code=1,
        )

        # Seed legacy-keyed masters for the *old* codes (5/1).
        MasterLicenseForm.objects.create(
            licensee_cat_code=5,
            licensee_scat_code=1,
            license_title="FL Bar Shop",
        )
        MasterLicenseFormTerms.objects.create(
            licensee_cat_code=5,
            licensee_scat_code=1,
            sl_no=1,
            license_terms="Term 1",
        )

        resolved_cat, resolved_scat = resolve_codes_for_license_form(cat.id, scat.id)
        self.assertEqual((resolved_cat, resolved_scat), (5, 1))

        # If codes don't exist as master PKs, treat as already-legacy.
        resolved_cat2, resolved_scat2 = resolve_codes_for_license_form(999, 888)
        self.assertEqual((resolved_cat2, resolved_scat2), (999, 888))
