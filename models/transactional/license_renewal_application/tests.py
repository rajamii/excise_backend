from django.test import TestCase
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from datetime import date
from django.utils import timezone
from decimal import Decimal

from auth.workflow.models import Workflow, WorkflowStage, WorkflowTransition, StagePermission
from auth.roles.models import Role
from .models import LicenseApplication
from models.masters.core.models import District, State, Subdivision, LicenseCategory, LicenseSubcategory
from models.masters.license.models import License
from models.masters.supply_chain.profile.models import UserManufacturingUnit
from models.transactional.payment_gateway.models import MasterPaymentModule, MasterHeadOfAccount, PaymentModuleHoa
from models.transactional.wallet.models import MasterWalletType, WalletBalance


class LicenseRenewalPrintResetTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user_model = get_user_model()

        # Create state, district, subdivision
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

        # Create category and subcategory
        self.category = LicenseCategory.objects.create(license_category="Test Category")
        self.subcategory = LicenseSubcategory.objects.create(description="FLR Shop", category=self.category)

        # Create roles
        self.licensee_role = Role.objects.create(name='licensee')
        self.level_1_role = Role.objects.create(name='level_1')

        # Create users
        self.licensee_user = self.user_model.objects.create_user(
            password='password123',
            email='licensee@example.com',
            role=self.licensee_role,
            district=self.district,
            subdivision=self.subdivision,
            phone_number="9999999901",
            first_name="Licensee",
            last_name="User",
            address="Test address 1"
        )
        self.licensee_user.username = 'licensee_user'
        self.licensee_user.save(update_fields=['username'])

        self.level_1_user = self.user_model.objects.create_user(
            password='password123',
            email='level_1@example.com',
            role=self.level_1_role,
            district=self.district,
            subdivision=self.subdivision,
            phone_number="9999999902",
            first_name="Officer",
            last_name="User",
            address="Test address 2"
        )
        self.level_1_user.username = 'level_1_user'
        self.level_1_user.save(update_fields=['username'])

        # Create workflow and stages
        self.workflow = Workflow.objects.create(name='License Approval')
        self.stages = {
            name: WorkflowStage.objects.create(workflow=self.workflow, name=name)
            for name in [
                'applicant_applied', 'awaiting_payment', 'approved'
            ]
        }
        self.stages['awaiting_payment'].description = "Awaiting License Fee Payment"
        self.stages['awaiting_payment'].save()

        # Create transitions
        WorkflowTransition.objects.create(
            workflow=self.workflow,
            from_stage=self.stages['applicant_applied'],
            to_stage=self.stages['awaiting_payment'],
            condition={}
        )
        WorkflowTransition.objects.create(
            workflow=self.workflow,
            from_stage=self.stages['awaiting_payment'],
            to_stage=self.stages['approved'],
            condition={}
        )

        # Create Head of Account mappings for wallet initialization
        self.wallet_type_fee = MasterWalletType.objects.create(
            code="license_fee",
            name="License Fee"
        )
        self.wallet_type_sec = MasterWalletType.objects.create(
            code="security_deposit",
            name="Security Deposit"
        )

        self.hoa = MasterHeadOfAccount.objects.create(
            sl_no=1,
            head_of_account="0039-00-150-01",
            major_head="0039",
            minor_head="150",
            detailed_head="01",
            detailed_head_driscription="License Fee Detail",
            visible_status=True
        )

        self.payment_module = MasterPaymentModule.objects.create(
            module_code="012",
            module_desc="other",  # matches module_type="other"
            license_fee=500.00,
            visibility_status=True
        )

        PaymentModuleHoa.objects.create(
            module_code=self.payment_module,
            wallet_type=self.wallet_type_fee,
            head_of_account=self.hoa,
            is_active=True
        )
        PaymentModuleHoa.objects.create(
            module_code=self.payment_module,
            wallet_type=self.wallet_type_sec,
            head_of_account=self.hoa,
            is_active=True
        )

        # Create a salesman license to renew
        self.salesman_license = License.objects.create(
            license_id="SB/225/2025-26/0001",
            source_type="salesman_barman",
            applicant=self.licensee_user,
            license_category=self.category,
            license_sub_category=self.subcategory,
            excise_district=self.district,
            issue_date=timezone.now(),
            valid_up_to=timezone.now() + timezone.timedelta(days=10),
            is_active=True,
            print_count=3,
            is_print_fee_paid=True,
            printed_on=timezone.now(),
            print_fee_paid_on=timezone.now(),
            validation_nonce="22800a7022710d1237e01b771560afe8",
            validation_nonce_updated_at=timezone.now()
        )

        # Create the renewal application for this license
        self.renewal_app = LicenseApplication.objects.create(
            application_id='LRA/225/2026-27/0001',
            workflow=self.workflow,
            current_stage=self.stages['awaiting_payment'],
            applicant=self.licensee_user,
            license_category=self.category,
            license_sub_category=self.subcategory,
            old_license_id=self.salesman_license.license_id,
            is_approved=False
        )

    def test_salesman_renewal_resets_print_count_and_validation_nonce(self):
        self.client.force_authenticate(user=self.licensee_user)
        
        # Verify initial values before renewal payment
        self.assertEqual(self.salesman_license.print_count, 3)
        self.assertTrue(self.salesman_license.is_print_fee_paid)
        self.assertIsNotNone(self.salesman_license.printed_on)
        self.assertEqual(self.salesman_license.validation_nonce, "22800a7022710d1237e01b771560afe8")
        self.assertIsNotNone(self.salesman_license.validation_nonce_updated_at)

        url = reverse('license_renewal_application:pay-license-fee-wallet', kwargs={
            'application_id': self.renewal_app.application_id
        })
        
        # Create WalletBalance directly for licensee_user
        WalletBalance.objects.create(
            licensee_id="licensee_user",
            user_id="licensee_user",
            module_type="other",
            wallet_type=self.wallet_type_fee,
            head_of_account="0039-00-150-01",
            current_balance=Decimal("1000.00")
        )

        response = self.client.post(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

        # Refresh the license from database
        self.salesman_license.refresh_from_db()

        # Check if print fields are reset to 0/None/default
        self.assertEqual(self.salesman_license.print_count, 0)
        self.assertFalse(self.salesman_license.is_print_fee_paid)
        self.assertNil(self.salesman_license.printed_on)
        self.assertEqual(self.salesman_license.validation_nonce, '')
        self.assertNil(self.salesman_license.validation_nonce_updated_at)
        self.assertNil(self.salesman_license.print_fee_paid_on)

    def assertNil(self, val):
        self.assertTrue(val is None or val == '')


from django.contrib.auth import get_user_model

class LicenseRenewalDashboardCountsTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user_model = get_user_model()

        self.state = State.objects.create(state="Sikkim", state_code=11, is_active=True)
        self.district = District.objects.create(district="Gangtok", district_code=225, is_active=True, state_code=self.state)
        self.subdivision = Subdivision.objects.create(subdivision="Gangtok Subdivision", subdivision_code=1553, is_active=True, district_code=self.district)

        self.category = LicenseCategory.objects.create(license_category="Test Category")
        self.subcategory = LicenseSubcategory.objects.create(description="FLR Shop", category=self.category)

        self.licensee_role = Role.objects.create(name='licensee')
        self.licensee_user = self.user_model.objects.create_user(
            password='password123',
            email='licensee@example.com',
            role=self.licensee_role,
            district=self.district,
            subdivision=self.subdivision,
            phone_number="9999999901",
            first_name="Licensee",
            last_name="User",
            address="Test address 1"
        )
        self.licensee_user.username = 'licensee_user'
        self.licensee_user.save(update_fields=['username'])

        self.workflow = Workflow.objects.create(id=1, name='License Approval')
        self.stages = {
            name: WorkflowStage.objects.create(workflow=self.workflow, name=name)
            for name in [
                'Applied', 'Awaiting Payment', 'approved', 'Objection'
            ]
        }
        
        self.client.force_authenticate(user=self.licensee_user)

    def test_dashboard_counts_separated_awaiting_payment(self):
        # Create one renewal application in Awaiting Payment stage
        LicenseApplication.objects.create(
            application_id='LRA/225/2026-27/0001',
            workflow=self.workflow,
            current_stage=self.stages['Awaiting Payment'],
            applicant=self.licensee_user,
            license_category=self.category,
            license_sub_category=self.subcategory,
            old_license_id="SB/225/2025-26/0001",
            is_approved=False
        )

        url = reverse("license_renewal_application:dashboard-counts")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data.get("awaiting_payment"), 1)
        self.assertEqual(resp.data.get("pending"), 0)

    def test_dashboard_counts_initial_pending(self):
        # Create one renewal application in Applied stage
        LicenseApplication.objects.create(
            application_id='LRA/225/2026-27/0002',
            workflow=self.workflow,
            current_stage=self.stages['Applied'],
            applicant=self.licensee_user,
            license_category=self.category,
            license_sub_category=self.subcategory,
            old_license_id="SB/225/2025-26/0002",
            is_approved=False
        )

        url = reverse("license_renewal_application:dashboard-counts")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data.get("awaiting_payment"), 0)
        self.assertEqual(resp.data.get("pending"), 1)