from datetime import date

from django.test import TestCase

from auth.user.models import CustomUser
from models.masters.core.models import District, LicenseCategory, LicenseSubcategory, State, Subdivision
from models.masters.license.models import License
from models.transactional.wallet.models import WalletBalance
from models.transactional.wallet.wallet_initializer import initialize_wallet_balances_for_license


class WalletInitializerPrimaryHolderTests(TestCase):
    def setUp(self):
        self.state = State.objects.create(state="Sikkim", state_code=11, is_active=True)
        self.district = District.objects.create(
            district="Gangtok",
            district_code=225,
            is_active=True,
            state_code=self.state,
        )
        self.subdivision = Subdivision.objects.create(
            subdivision="Gangtok Subdivision",
            subdivision_code=1553,
            is_active=True,
            district_code=self.district,
        )
        self.user = CustomUser.objects.create_user(
            email="u1@example.com",
            first_name="Test",
            last_name="User",
            phone_number="9999999999",
            district=self.district,
            subdivision=self.subdivision,
            address="Test address",
            password="pass",
        )
        # Keep username deterministic for wallet user_id grouping.
        self.user.username = "TH0001"
        self.user.save(update_fields=["username"])

        self.cat = LicenseCategory.objects.create(license_category="Test Category")
        self.sub_other = LicenseSubcategory.objects.create(description="FLR Shop", category=self.cat)
        self.sub_distillery = LicenseSubcategory.objects.create(description="Distillery Unit", category=self.cat)

    def _create_license(self, *, license_id: str, source_type: str, subcategory: LicenseSubcategory) -> License:
        return License.objects.create(
            license_id=license_id,
            source_type=source_type,
            applicant=self.user,
            license_category=self.cat,
            license_sub_category=subcategory,
            excise_district=self.district,
            issue_date=date(2026, 4, 1),
            valid_up_to=date(2027, 3, 31),
            is_active=True,
        )

    def test_retail_then_distillery_adds_only_missing_wallets(self):
        retail = self._create_license(
            license_id="LA/225/2025-26/0001",
            source_type="license_application",
            subcategory=self.sub_other,
        )
        initialize_wallet_balances_for_license(retail)

        self.assertEqual(WalletBalance.objects.filter(user_id__iexact="TH0001").count(), 2)
        self.assertEqual(
            set(WalletBalance.objects.filter(user_id__iexact="TH0001").values_list("wallet_type", flat=True)),
            {"security_deposit", "license_fee"},
        )
        self.assertEqual(
            set(WalletBalance.objects.filter(user_id__iexact="TH0001").values_list("module_type", flat=True)),
            {"other"},
        )

        distillery = self._create_license(
            license_id="NA/225/2025-26/0002",
            source_type="new_license_application",
            subcategory=self.sub_distillery,
        )
        initialize_wallet_balances_for_license(distillery)

        rows = WalletBalance.objects.filter(user_id__iexact="TH0001")
        self.assertEqual(rows.count(), 5)
        self.assertEqual(
            set(rows.values_list("wallet_type", flat=True)),
            {"excise", "education_cess", "hologram", "security_deposit", "license_fee"},
        )
        # After NA issuance, wallets should converge to NA/... as primary licensee_id.
        self.assertTrue(all(str(r.licensee_id).startswith("NA/") for r in rows))

    def test_distillery_then_retail_does_not_create_duplicate_rows(self):
        distillery = self._create_license(
            license_id="NA/225/2025-26/0003",
            source_type="new_license_application",
            subcategory=self.sub_distillery,
        )
        initialize_wallet_balances_for_license(distillery)
        self.assertEqual(WalletBalance.objects.filter(user_id__iexact="TH0001").count(), 5)

        retail = self._create_license(
            license_id="LA/225/2025-26/0004",
            source_type="license_application",
            subcategory=self.sub_other,
        )
        initialize_wallet_balances_for_license(retail)

        # Still only 5 wallets (2 common + 3 manufacturing), no new duplicates.
        rows = WalletBalance.objects.filter(user_id__iexact="TH0001")
        self.assertEqual(rows.count(), 5)
        self.assertEqual(rows.filter(wallet_type="security_deposit").count(), 1)
        self.assertEqual(rows.filter(wallet_type="license_fee").count(), 1)
