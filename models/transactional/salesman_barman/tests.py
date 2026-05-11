from django.test import TestCase

from auth.workflow.models import Workflow, WorkflowStage
from models.masters.core.models import District, LicenseCategory, State

from .models import SalesmanBarmanModel
from .serializers import SalesmanBarmanSerializer

# Create your tests here.


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
