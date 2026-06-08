from django.test import TestCase
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model
from django.urls import reverse

from auth.workflow.models import Workflow, WorkflowStage
from auth.roles.models import Role
from .models import NewLicenseApplication
from models.masters.core.models import (
    District,
    State,
    Subdivision,
    LicenseCategory,
    LicenseSubcategory,
    LicenseType,
    PoliceStation
)

class NewLicenseDashboardCountsTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user_model = get_user_model()

        self.state = State.objects.create(state="Sikkim", state_code=11, is_active=True)
        self.district = District.objects.create(district="Gangtok", district_code=225, is_active=True, state_code=self.state)
        self.subdivision = Subdivision.objects.create(subdivision="Gangtok Subdivision", subdivision_code=1553, is_active=True, district_code=self.district)
        self.police_station = PoliceStation.objects.create(police_station="Gangtok PS", subdivision_code=self.subdivision)

        self.category = LicenseCategory.objects.create(license_category="Test Category")
        self.subcategory = LicenseSubcategory.objects.create(description="FLR Shop", category=self.category)
        self.license_type = LicenseType.objects.create(license_type="Retail")

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

    def _create_application(self, application_id, stage):
        return NewLicenseApplication.objects.create(
            application_id=application_id,
            workflow=self.workflow,
            current_stage=stage,
            applicant=self.licensee_user,
            license_type=self.license_type,
            license_category=self.category,
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
            is_application_fee_paid=True
        )

    def test_dashboard_counts_separated_awaiting_payment(self):
        self._create_application('NA/225/2026-27/0001', self.stages['Awaiting Payment'])

        url = reverse("new_license_application:dashboard-counts")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data.get("awaiting_payment"), 1)
        self.assertEqual(resp.data.get("pending"), 0)

    def test_dashboard_counts_initial_pending(self):
        self._create_application('NA/225/2026-27/0002', self.stages['Applied'])

        url = reverse("new_license_application:dashboard-counts")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data.get("awaiting_payment"), 0)
        self.assertEqual(resp.data.get("pending"), 1)
