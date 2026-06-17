from datetime import date, datetime

from django.test import TestCase
from rest_framework.test import APIClient
from django.urls import reverse
from django.utils import timezone

from auth.user.models import CustomUser
from models.masters.core.models import District, LicenseCategory, LicenseSubcategory, State, Subdivision
from models.masters.license.models import License
from models.transactional.wallet.models import WalletBalance
from models.transactional.wallet.wallet_initializer import initialize_wallet_balances_for_license, _resolve_module_type


def _create_hoa_mappings():
    from models.transactional.payment_gateway.models import MasterHeadOfAccount, MasterPaymentModule, PaymentModuleHoa
    from models.transactional.wallet.models import MasterWalletType

    # Create Wallet Types
    wallet_types = ["excise", "education_cess", "hologram", "security_deposit", "license_fee"]
    wallet_type_objs = {}
    for wt in wallet_types:
        obj, _ = MasterWalletType.objects.get_or_create(
            code=wt,
            defaults={"name": wt.replace("_", " ").title(), "is_active": True}
        )
        wallet_type_objs[wt] = obj

    # Create Payment Modules
    module_types = ["distillery", "other"]
    module_objs = {}
    for mt in module_types:
        obj, _ = MasterPaymentModule.objects.get_or_create(
            module_code=f"PM_{mt.upper()}",
            defaults={"module_desc": f"Module {mt}", "visibility_status": True}
        )
        module_objs[mt] = obj

    # Create Head of Account mappings
    sl_no = 1
    for mt in module_types:
        wts = wallet_types if mt == "distillery" else ["security_deposit", "license_fee"]
        for wt in wts:
            hoa_str = f"HOA-{mt}-{wt}"
            hoa, _ = MasterHeadOfAccount.objects.get_or_create(
                sl_no=sl_no,
                defaults={
                    "head_of_account": hoa_str,
                    "major_head": "0039",
                    "minor_head": "105",
                    "detailed_head": "45",
                    "detailed_head_driscription": f"Description for {hoa_str}",
                    "visible_status": True
                }
            )
            sl_no += 1
            
            PaymentModuleHoa.objects.get_or_create(
                module_code=module_objs[mt],
                wallet_type=wallet_type_objs[wt],
                head_of_account=hoa,
                defaults={"is_active": True}
            )



class WalletInitializerPrimaryHolderTests(TestCase):
    def setUp(self):
        _create_hoa_mappings()
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

    def test_salesman_barman_without_subcategory_resolves_other_without_warning(self):
        license_obj = License.objects.create(
            license_id="SB/225/2026-27/0001",
            source_type="salesman_barman",
            applicant=self.user,
            license_category=self.cat,
            license_sub_category=None,
            excise_district=self.district,
            issue_date=timezone.make_aware(datetime(2026, 4, 1)),
            valid_up_to=timezone.make_aware(datetime(2027, 3, 31, 23, 59, 59)),
            is_active=True,
        )

        with self.assertNoLogs("models.transactional.wallet.wallet_initializer", level="WARNING"):
            self.assertEqual(_resolve_module_type(license_obj), "other")


class WalletSummaryScopeFilteringTests(TestCase):
    def setUp(self):
        _create_hoa_mappings()
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
            email="u2@example.com",
            first_name="Test",
            last_name="User",
            phone_number="9999999998",
            district=self.district,
            subdivision=self.subdivision,
            address="Test address",
            password="pass",
        )
        self.user.username = "TH0002"
        self.user.save(update_fields=["username"])

        self.cat = LicenseCategory.objects.create(license_category="Test Category")
        self.sub_distillery = LicenseSubcategory.objects.create(description="Distillery Unit", category=self.cat)
        self.license = License.objects.create(
            license_id="NA/225/2025-26/0100",
            source_type="new_license_application",
            applicant=self.user,
            license_category=self.cat,
            license_sub_category=self.sub_distillery,
            excise_district=self.district,
            issue_date=date(2026, 4, 1),
            valid_up_to=date(2027, 3, 31),
            is_active=True,
        )
        initialize_wallet_balances_for_license(self.license)
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def _summary(self, **params):
        url = reverse("payment:wallet-summary", kwargs={"licensee_id": self.license.license_id})
        return self.client.get(url, params)

    def test_scope_wallets_excludes_license_wallets(self):
        resp = self._summary(scope="wallets")
        self.assertEqual(resp.status_code, 200)
        wallet_types = {row.get("wallet_type") for row in resp.data.get("results", [])}
        self.assertTrue({"excise", "education_cess", "hologram"}.issubset(wallet_types))
        self.assertFalse({"license_fee", "security_deposit"} & wallet_types)
        self.assertEqual(resp.data.get("count"), 3)

    def test_scope_license_includes_only_license_wallets(self):
        resp = self._summary(scope="license")
        self.assertEqual(resp.status_code, 200)
        wallet_types = {row.get("wallet_type") for row in resp.data.get("results", [])}
        self.assertEqual(wallet_types, {"license_fee", "security_deposit"})
        self.assertEqual(resp.data.get("count"), 2)


class WalletRechargeFallbackTests(TestCase):
    def setUp(self):
        from decimal import Decimal
        from models.masters.core.models import PoliceStation, LicenseType
        from auth.workflow.models import Workflow, WorkflowStage
        from models.transactional.new_license_application.models import NewLicenseApplication
        from models.transactional.wallet.models import WalletBalance, MasterWalletType

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
        self.police_station = PoliceStation.objects.create(
            police_station="Gangtok PS",
            subdivision_code=self.subdivision
        )
        self.user = CustomUser.objects.create_user(
            email="u3@example.com",
            first_name="Test",
            last_name="User",
            phone_number="9999999903",
            district=self.district,
            subdivision=self.subdivision,
            address="Test address",
            password="pass",
        )
        self.user.username = "TH0003"
        self.user.save(update_fields=["username"])

        self.cat = LicenseCategory.objects.create(license_category="Test Category")
        self.subcategory = LicenseSubcategory.objects.create(description="FLR Shop", category=self.cat)
        self.license_type = LicenseType.objects.create(license_type="Retail")

        # Create an existing active license for the user
        self.license = License.objects.create(
            license_id="NA/225/2026-27/0010",
            source_type="new_license_application",
            applicant=self.user,
            license_category=self.cat,
            license_sub_category=self.subcategory,
            excise_district=self.district,
            issue_date=date(2026, 4, 1),
            valid_up_to=date(2027, 3, 31),
            is_active=True,
        )

        # Initialize MasterWalletType and the dummy WalletBalance row for the active license
        wallet_type_obj, _ = MasterWalletType.objects.get_or_create(code="security_deposit", defaults={"description": "Security Deposit"})
        WalletBalance.objects.create(
            licensee_id="NA/225/2026-27/0010",
            licensee_name="Test User",
            user_id="TH0003",
            module_type="other",
            wallet_type=wallet_type_obj,
            head_of_account="non",
            current_balance=Decimal("0.00"),
        )

        self.workflow = Workflow.objects.create(id=2, name='License Approval 2')
        self.stage = WorkflowStage.objects.create(workflow=self.workflow, name='Awaiting Payment')
        self.approved_stage = WorkflowStage.objects.create(workflow=self.workflow, name='Approved', is_final=True)

        # Create a pending NewLicenseApplication for this user
        self.app = NewLicenseApplication.objects.create(
            application_id="NLI/225/2026-27/0011",
            workflow=self.workflow,
            current_stage=self.stage,
            applicant=self.user,
            license_type=self.license_type,
            license_category=self.cat,
            license_sub_category=self.subcategory,
            establishment_name="Test Est",
            site_type="New",
            applicant_name="Test Applicant",
            father_husband_name="Test Father",
            dob="2000-01-01",
            gender="Male",
            nationality="Indian",
            residential_status="Resident",
            present_address="Present Address",
            permanent_address="Permanent Address",
            pan="ABCDE1234F",
            email="test@example.com",
            mobile_number="9999999999",
            mode_of_operation="Self",
            has_sikkim_certificate="Yes",
            has_excise_license="No",
            criminal_conviction="No",
            site_district=self.district,
            site_subdivision=self.subdivision,
            police_station=self.police_station,
            location_category="Urban",
            location_name="Gangtok",
            ward_name="Ward 1",
            business_address="Business Address",
            road_name="Road 1",
            pin_code="737101",
            construction_type="Permanent",
            site_owned="Yes",
            noc_obtained="Yes",
            is_application_fee_paid=True,
            is_license_fee_paid=False,
            is_security_fee_paid=False,
        )

        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_security_deposit_recharge_fallback(self):
        # We recharge using the active license ID (e.g. NA/225/2026-27/0010)
        url = reverse("payment:wallet-recharge-credit", kwargs={"licensee_id": self.license.license_id})
        payload = {
            "transaction_id": "TXN_TEST_123",
            "wallet_type": "security_deposit",
            "head_of_account": "non",
            "amount": "1000.00",
            "remarks": "Test recharge"
        }
        resp = self.client.post(url, payload, format="json")
        self.assertEqual(resp.status_code, 200)

        # Refresh from DB to verify that the pending application's security deposit status is updated
        self.app.refresh_from_db()
        self.assertTrue(self.app.is_security_fee_paid)

    def test_security_deposit_recharge_fallback_transitions_stage(self):
        # Pre-mark license fee as paid, so that completing security deposit triggers Approved stage transition
        self.app.is_license_fee_paid = True
        self.app.save(update_fields=["is_license_fee_paid"])

        url = reverse("payment:wallet-recharge-credit", kwargs={"licensee_id": self.license.license_id})
        payload = {
            "transaction_id": "TXN_TEST_456",
            "wallet_type": "security_deposit",
            "head_of_account": "non",
            "amount": "1000.00",
            "remarks": "Test recharge"
        }
        resp = self.client.post(url, payload, format="json")
        self.assertEqual(resp.status_code, 200)

        self.app.refresh_from_db()
        self.assertTrue(self.app.is_security_fee_paid)
        self.assertTrue(self.app.is_license_fee_paid)
        # The stage should be transitioned to Approved (final stage)
        self.assertEqual(self.app.current_stage_id, self.approved_stage.id)
        self.assertTrue(self.app.is_approved)
