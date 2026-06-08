from django.test import TestCase

from auth.workflow.models import Workflow, WorkflowStage
from models.masters.core.models import District, LicenseCategory, State, Subdivision

from .models import SalesmanBarmanModel
from .serializers import SalesmanBarmanSerializer

from rest_framework.test import APIClient
from django.urls import reverse
from auth.roles.models import Role
from auth.user.models import CustomUser


class SalesmanBarmanSerializerPartialUpdateTests(TestCase):
    def test_partial_update_does_not_require_all_fields(self):
        workflow = Workflow.objects.create(name="Salesman/Barman Test Workflow")
        stage = WorkflowStage.objects.create(workflow=workflow, name="draft", is_initial=True)

        state = State.objects.create(state="Sikkim", state_code=11)
        district = District.objects.create(district="Gangtok", district_code=1101, state_code=state)
        license_category = LicenseCategory.objects.create(license_category="SBM")

        application = SalesmanBarmanModel.objects.create(
            application_id="SBM/1101/2026-27/0001",
            workflow=workflow,
            current_stage=stage,
            excise_district=district,
            license_category=license_category,
        )

        serializer = SalesmanBarmanSerializer(
            application,
            data={"aadhaar": "999999999999"},
            partial=True,
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)


class SalesmanBarmanDashboardCountsTests(TestCase):
    def setUp(self):
        self.state = State.objects.create(state="Sikkim", state_code=11)
        self.district = District.objects.create(district="Gangtok", district_code=1101, state_code=self.state)
        self.subdivision = Subdivision.objects.create(
            subdivision="Gangtok Subdivision",
            subdivision_code=1553,
            is_active=True,
            district_code=self.district,
        )
        self.license_category = LicenseCategory.objects.create(license_category="SBM")

        # Create Role
        self.role = Role.objects.create(name="Licensee")

        # Create User
        self.user = CustomUser.objects.create_user(
            email="licensee@example.com",
            first_name="Test",
            last_name="Licensee",
            phone_number="8888888888",
            password="pass",
            role=self.role,
            district=self.district,
            subdivision=self.subdivision,
            address="Test address",
        )
        self.user.username = "TS0001"
        self.user.save(update_fields=["username"])

        # Create Workflow and Stages
        self.workflow = Workflow.objects.create(id=2, name="Salesman/Barman Workflow")
        self.stage_initial = WorkflowStage.objects.create(
            workflow=self.workflow, name="Applicant Applied", is_initial=True
        )
        self.stage_payment = WorkflowStage.objects.create(
            workflow=self.workflow, name="Awaiting Payment"
        )
        self.stage_approved = WorkflowStage.objects.create(
            workflow=self.workflow, name="Approved", is_final=True
        )
        self.stage_objection = WorkflowStage.objects.create(
            workflow=self.workflow, name="Objection"
        )

        # Setup API Client
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_dashboard_counts_separated_awaiting_payment(self):
        # Create one salesman_barman application in Awaiting Payment stage
        SalesmanBarmanModel.objects.create(
            application_id="SBM/1101/2026-27/0001",
            workflow=self.workflow,
            current_stage=self.stage_payment,
            excise_district=self.district,
            license_category=self.license_category,
            applicant=self.user,
        )

        url = reverse("salesman_barman:sb-dashboard-counts")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data.get("awaiting_payment"), 1)
        self.assertEqual(resp.data.get("pending"), 0)

    def test_dashboard_counts_initial_pending(self):
        # Create one application in Applicant Applied stage
        SalesmanBarmanModel.objects.create(
            application_id="SBM/1101/2026-27/0002",
            workflow=self.workflow,
            current_stage=self.stage_initial,
            excise_district=self.district,
            license_category=self.license_category,
            applicant=self.user,
        )

        url = reverse("salesman_barman:sb-dashboard-counts")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data.get("awaiting_payment"), 0)
        self.assertEqual(resp.data.get("pending"), 1)

