from datetime import date, datetime
from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient
from django.urls import reverse
from django.utils import timezone

from auth.user.models import CustomUser
from models.masters.core.models import District, LicenseCategory, LicenseSubcategory, State, Subdivision
from models.masters.license.models import License
from models.transactional.wallet.models import WalletBalance, MasterWalletType
from models.transactional.payment_gateway.models import MasterPaymentModule, MasterHeadOfAccount, PaymentModuleHoa
from models.transactional.wallet.wallet_initializer import initialize_wallet_balances_for_license, _resolve_module_type


def _seed_module_hoa_for_tests():
    modules = {
        "001": ("distillery", "Distillery"),
        "002": ("brewery", "Brewery"),
        "003": ("bottling", "Bottling"),
        "004": ("wholesale", "Wholesale"),
        "005": ("retail", "Retail"),
        "006": ("bar", "Bar"),
        "007": ("hotel", "Hotel"),
        "008": ("club", "Club"),
        "009": ("other", "Other"),
    }
    wallets = [
        ("excise", "Excise Duty"),
        ("education_cess", "Education Cess"),
        ("hologram", "Hologram Fee"),
        ("security_deposit", "Security Deposit"),
        ("license_fee", "License Fee"),
    ]
    hoa, _ = MasterHeadOfAccount.objects.get_or_create(
        sl_no=1,
        defaults={
            "head_of_account": "0039001010100",
            "major_head": "0039",
            "minor_head": "101",
            "detailed_head": "00",
            "detailed_head_driscription": "State Excise Test HOA",
            "visible_status": True,
        }
    )
    for code, (m_type, desc) in modules.items():
        pm, _ = MasterPaymentModule.objects.get_or_create(
            module_code=code,
            defaults={"module_desc": m_type, "visibility_status": True}
        )
        for w_code, w_name in wallets:
            wt, _ = MasterWalletType.objects.get_or_create(
                code=w_code,
                defaults={"name": w_name, "is_active": True}
            )
            PaymentModuleHoa.objects.get_or_create(
                module_code=pm,
                wallet_type=wt,
                defaults={"head_of_account": hoa, "is_active": True}
            )


class WalletInitializerPrimaryHolderTests(TestCase):
    def setUp(self):
        _seed_module_hoa_for_tests()
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
        _seed_module_hoa_for_tests()
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
            police_station_code=22501,
            district_code=self.district,
            is_active=True,
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

        self.workflow, _ = Workflow.objects.get_or_create(id=2, defaults={'name': 'License Approval 2'})
        self.stage, _ = WorkflowStage.objects.get_or_create(workflow=self.workflow, name='Awaiting Payment')
        self.approved_stage, _ = WorkflowStage.objects.get_or_create(workflow=self.workflow, name='Approved', defaults={'is_final': True})

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


class WalletInitializerSalesmanBarmanTests(TestCase):
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
            email="u3@example.com",
            first_name="Test",
            last_name="User",
            phone_number="9999999997",
            district=self.district,
            subdivision=self.subdivision,
            address="Test address",
            password="pass",
        )
        self.user.username = "TH0003"
        self.user.save(update_fields=["username"])

        self.cat = LicenseCategory.objects.create(license_category="Test Category")
        self.sub_other = LicenseSubcategory.objects.create(description="FLR Shop", category=self.cat)

        # Seed HOA and Payment Module dependencies
        from models.transactional.payment_gateway.models import MasterPaymentModule, PaymentModuleHoa, MasterHeadOfAccount
        from models.transactional.wallet.models import MasterWalletType

        mpm, _ = MasterPaymentModule.objects.get_or_create(module_code="other_module", defaults={"module_desc": "other"})
        wt_sd, _ = MasterWalletType.objects.get_or_create(code="security_deposit", defaults={"name": "Security Deposit"})
        wt_lf, _ = MasterWalletType.objects.get_or_create(code="license_fee", defaults={"name": "License Fee"})
        hoa_sd, _ = MasterHeadOfAccount.objects.get_or_create(sl_no=1, defaults={"head_of_account": "non", "visible_status": True})
        hoa_lf, _ = MasterHeadOfAccount.objects.get_or_create(sl_no=2, defaults={"head_of_account": "0039-00-800-45-02", "visible_status": True})

        PaymentModuleHoa.objects.get_or_create(
            module_code=mpm,
            wallet_type=wt_sd,
            head_of_account=hoa_sd,
            defaults={"is_active": True}
        )
        PaymentModuleHoa.objects.get_or_create(
            module_code=mpm,
            wallet_type=wt_lf,
            head_of_account=hoa_lf,
            defaults={"is_active": True}
        )

    def test_sb_license_initialization_resolves_to_inactive_na_license(self):
        # 1. Create an inactive NA/ license for the user (representing the pending new license application)
        na_license = License.objects.create(
            license_id="NA/225/2025-26/0005",
            source_type="new_license_application",
            applicant=self.user,
            license_category=self.cat,
            license_sub_category=self.sub_other,
            excise_district=self.district,
            issue_date=date(2026, 4, 1),
            valid_up_to=date(2027, 3, 31),
            is_active=False, # Inactive
        )

        # 2. Create the salesman/barman license (representing the subordinate license)
        sb_license = License.objects.create(
            license_id="SB/225/2025-26/0001",
            source_type="salesman_barman",
            applicant=self.user,
            license_category=self.cat,
            license_sub_category=None,
            excise_district=self.district,
            issue_date=date(2026, 4, 1),
            valid_up_to=date(2027, 3, 31),
            is_active=True,
        )

        # 3. Initialize wallet balances for the salesman/barman license.
        # It should resolve to the applicant's NA/ license ID (even if it's inactive) rather than SB/.
        initialize_wallet_balances_for_license(sb_license)

        # 4. Verify wallet balances are created with licensee_id = NA/...
        rows = WalletBalance.objects.filter(user_id__iexact="TH0003")
        self.assertEqual(rows.count(), 2)
        for r in rows:
            self.assertEqual(r.licensee_id, "NA/225/2025-26/0005")


class SecurityDepositRecordTests(TestCase):
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
            email="deposit_user@example.com",
            first_name="Deposit",
            last_name="Tester",
            phone_number="9876543210",
            district=self.district,
            subdivision=self.subdivision,
            address="Test address",
            password="pass",
        )
        self.user.username = "DEP_USER_01"
        self.user.save(update_fields=["username"])

        from models.transactional.wallet.models import SecurityDepositRecord
        self.SecurityDepositRecord = SecurityDepositRecord

    def test_security_deposit_record_balance_and_status_auto_calculation(self):
        # 1. Create a security deposit record with 10,000 deposit
        rec = self.SecurityDepositRecord.objects.create(
            user=self.user,
            applicant_user_id=str(self.user.id),
            username=self.user.username,
            applicant_name="Deposit Tester",
            application_id="NLI/GTK/2026-27/0001",
            license_id="NA/225/2026-27/0001",
            establishment_name="Test Hotel Bar",
            amount=10000.00,
            transaction_id="TXN-SD-12345",
        )

        self.assertEqual(rec.balance_amount, 10000.00)
        self.assertEqual(rec.status, "PAID")
        self.assertEqual(rec.refunded_amount, 0.00)
        self.assertIsNotNone(rec.from_date)

        # 2. Simulate partial refund (e.g. 4000 refunded back)
        rec.refunded_amount = 4000.00
        rec.save()

        rec.refresh_from_db()
        self.assertEqual(rec.balance_amount, 6000.00)
        self.assertEqual(rec.status, "PARTIALLY_REFUNDED")

        # 3. Simulate full refund (e.g. remaining 6000 refunded, total 10000)
        rec.from_date = date(2026, 1, 1)
        rec.to_date = date(2026, 7, 1)
        rec.refunded_amount = 10000.00
        rec.save()

        rec.refresh_from_db()
        self.assertEqual(rec.balance_amount, 0.00)
        self.assertEqual(rec.status, "REFUNDED")
        self.assertEqual(rec.from_date, date(2026, 1, 1))
        self.assertEqual(rec.to_date, date(2026, 7, 1))
        self.assertEqual(rec.deposit_duration_days, 181)

    def test_create_or_update_security_deposit_record_helper(self):
        from models.transactional.wallet.wallet_service import create_or_update_security_deposit_record

        # 1. Test creation via helper
        rec = create_or_update_security_deposit_record(
            user=self.user,
            username=self.user.username,
            applicant_name="Deposit Tester",
            application_id="NLI/GTK/2026-27/0002",
            establishment_name="Hillside Lounge",
            amount=5000.00,
            transaction_id="TXN-SD-99999",
            remarks="Security fee paid for NLI/GTK/2026-27/0002",
        )

        self.assertIsNotNone(rec)
        self.assertEqual(rec.application_id, "NLI/GTK/2026-27/0002")
        self.assertEqual(rec.amount, 5000.00)
        self.assertEqual(rec.balance_amount, 5000.00)
        self.assertEqual(rec.status, "PAID")
        self.assertEqual(rec.establishment_name, "Hillside Lounge")

        # 2. Test updating same application does not create duplicate
        rec2 = create_or_update_security_deposit_record(
            application_id="NLI/GTK/2026-27/0002",
            license_id="NA/225/2026-27/0002",
            amount=5000.00,
        )

        self.assertEqual(rec.pk, rec2.pk)
        self.assertEqual(rec2.license_id, "NA/225/2026-27/0002")
        self.assertEqual(self.SecurityDepositRecord.objects.filter(application_id="NLI/GTK/2026-27/0002").count(), 1)

    def test_auto_creates_security_deposit_record_on_application_payment(self):
        from models.masters.core.models import LicenseType, PoliceStation
        from auth.workflow.models import Workflow, WorkflowStage
        from models.transactional.new_license_application.models import NewLicenseApplication
        from models.transactional.payment_gateway.models import MasterPaymentModule, PaymentModuleHoa, MasterHeadOfAccount
        from models.transactional.wallet.models import MasterWalletType, WalletBalance

        cat = LicenseCategory.objects.create(license_category="Bar Cat")
        subcat = LicenseSubcategory.objects.create(description="Bar Sub", category=cat)
        ltype = LicenseType.objects.create(license_type="Retail Bar")
        wf = Workflow.objects.create(id=10, name='Approval Flow')
        st_wait = WorkflowStage.objects.create(workflow=wf, name='Awaiting Payment')
        st_app = WorkflowStage.objects.create(workflow=wf, name='Approved', is_final=True)
        ps = PoliceStation.objects.create(police_station="Test PS", police_station_code=99881, district_code=self.district, is_active=True)

        app = NewLicenseApplication.objects.create(
            application_id="NLI/GTK/2026-27/0099",
            workflow=wf,
            current_stage=st_wait,
            applicant=self.user,
            applicant_name="Deposit Tester",
            license_type=ltype,
            license_category=cat,
            license_sub_category=subcat,
            establishment_name="Skyview Bar",
            site_district=self.district,
            site_subdivision=self.subdivision,
            police_station=ps,
            location_category="Urban",
            is_application_fee_paid=True,
            is_license_fee_paid=False,
            is_security_fee_paid=False,
        )

        # Pre-seed wallet type & HOA
        wt, _ = MasterWalletType.objects.get_or_create(code="security_deposit", defaults={"name": "Security Deposit"})
        hoa, _ = MasterHeadOfAccount.objects.get_or_create(sl_no=101, defaults={"head_of_account": "non", "visible_status": True})
        mpm, _ = MasterPaymentModule.objects.get_or_create(module_code="other_module", defaults={"module_desc": "other"})
        PaymentModuleHoa.objects.get_or_create(module_code=mpm, wallet_type=wt, head_of_account=hoa, defaults={"is_active": True})

        WalletBalance.objects.create(
            licensee_id=app.application_id,
            licensee_name="Deposit Tester",
            user_id=self.user.username,
            module_type="other",
            wallet_type=wt,
            head_of_account="non",
            current_balance=Decimal("0.00"),
        )

        client = APIClient()
        client.force_authenticate(user=self.user)

        # Trigger security deposit payment recharge
        url = reverse("payment:wallet-recharge-credit", kwargs={"licensee_id": app.application_id})
        payload = {
            "transaction_id": "TXN_SD_E2E_001",
            "wallet_type": "security_deposit",
            "head_of_account": "non",
            "amount": "15000.00",
            "remarks": "Security deposit payment for application",
        }
        resp = client.post(url, payload, format="json")
        self.assertEqual(resp.status_code, 200)

        # Check application updated
        app.refresh_from_db()
        self.assertTrue(app.is_security_fee_paid)

        # Check SecurityDepositRecord was automatically created
        record = self.SecurityDepositRecord.objects.filter(application_id="NLI/GTK/2026-27/0099").first()
        self.assertIsNotNone(record)
        self.assertEqual(record.username, self.user.username)
        self.assertEqual(record.establishment_name, "Skyview Bar")
        self.assertEqual(record.amount, 15000.00)
        self.assertEqual(record.balance_amount, 15000.00)
        self.assertEqual(record.status, "PAID")
        self.assertEqual(record.transaction_id, "TXN_SD_E2E_001")

    def test_security_deposit_record_list_and_deduction(self):
        from models.transactional.wallet.models import SecurityDepositRecord
        from models.masters.license.models import License

        from models.masters.core.models import LicenseType, PoliceStation
        from auth.workflow.models import Workflow, WorkflowStage
        from models.transactional.new_license_application.models import NewLicenseApplication

        cat = LicenseCategory.objects.create(license_category="Bar Cat 2")
        subcat = LicenseSubcategory.objects.create(description="Bar Sub 2", category=cat)
        ltype = LicenseType.objects.create(license_type="Bar Type")
        wf = Workflow.objects.create(name="License Test Workflow")
        st_app = WorkflowStage.objects.create(workflow=wf, name="Approved", is_final=True)
        ps = PoliceStation.objects.create(police_station="Test PS 2", police_station_code=99882, district_code=self.district, is_active=True)

        app = NewLicenseApplication.objects.create(
            application_id="NLI/GTK/2026-27/0099",
            workflow=wf,
            current_stage=st_app,
            applicant=self.user,
            applicant_name="Deposit Tester",
            license_type=ltype,
            license_category=cat,
            license_sub_category=subcat,
            establishment_name="Skyview Bar",
            site_district=self.district,
            site_subdivision=self.subdivision,
            police_station=ps,
            location_category="Urban",
            is_application_fee_paid=True,
            is_license_fee_paid=True,
            is_security_fee_paid=True,
            is_approved=True,
        )

        lic = License.objects.create(
            license_id="NA/01/2026-27/0055",
            applicant=self.user,
            license_category=cat,
            license_sub_category=subcat,
            excise_district=self.district,
            issue_date=timezone.now(),
            valid_up_to=timezone.now() + timezone.timedelta(days=365),
            is_active=True,
            source_type="new_license_application",
            source_object_id="NLI/GTK/2026-27/0099"
        )

        record = SecurityDepositRecord.objects.create(
            user=self.user,
            applicant_user_id=str(self.user.pk),
            username=self.user.username,
            applicant_name="Deposit Tester",
            application_id="NLI/GTK/2026-27/0099",
            license_id="NA/01/2026-27/0055",
            establishment_name="Skyview Bar",
            amount=Decimal("20000.00"),
            status="PAID"
        )

        admin_user = CustomUser.objects.create_superuser(
            username="admin_sec_tester",
            email="admin_sec@example.com",
            password="adminpassword123",
            first_name="Admin",
            last_name="SecTester",
            phone_number="8877665544",
        )

        client = APIClient()
        client.force_authenticate(user=admin_user)

        # GET security deposit records
        list_url = reverse("payment:security-deposit-records-list")
        resp = client.get(list_url)
        self.assertEqual(resp.status_code, 200)
        self.assertGreaterEqual(resp.data["count"], 1)

        # POST deduct security deposit
        deduct_url = reverse("payment:security-deposit-record-deduct", kwargs={"pk": record.pk})
        deduct_payload = {
            "deduct_amount": 20000.00,
            "remarks": "Violation penalty - cancel license",
            "action_type": "DEDUCTED"
        }
        resp = client.post(deduct_url, deduct_payload, format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["status"], "success")

        # Verify record updated
        record.refresh_from_db()
        self.assertEqual(record.status, "DEDUCTED")
        self.assertEqual(record.balance_amount, Decimal("0.00"))
        self.assertEqual(record.refunded_amount, Decimal("20000.00"))
        self.assertIsNotNone(record.to_date)

        # Verify license is suspended
        lic.refresh_from_db()
        self.assertFalse(lic.is_active)

        # Verify application is moved to Terminated stage
        app.refresh_from_db()
        self.assertEqual(app.current_stage.name, "Terminated")
        self.assertFalse(app.is_security_fee_paid)
        self.assertFalse(app.is_approved)



