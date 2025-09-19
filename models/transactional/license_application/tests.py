from django.test import TestCase
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model
from auth.workflow.models import Workflow, WorkflowStage, WorkflowTransition, StagePermission
from auth.roles.models import Role
from .models import LicenseApplication
from django.urls import reverse
from rest_framework import status

class AdvanceLicenseApplicationTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user_model = get_user_model()
        
        # Create workflow and stages
        self.workflow = Workflow.objects.create(name='License Approval')
        self.stages = {
            name: WorkflowStage.objects.create(workflow=self.workflow, name=name)
            for name in [
                'applicant_applied', 'level_1', 'level_2', 'level_3', 'level_4', 'level_5',
                'level_1_objection', 'approved'
            ]
        }
        
        # Create roles
        self.roles = {
            name: Role.objects.create(name=name)
            for name in ['licensee', 'level_1', 'level_2', 'level_3']
        }
        
        # Create users
        self.users = {
            name: self.user_model.objects.create(username=f'{name}_user', role=role)
            for name, role in self.roles.items()
        }
        
        # Create StagePermissions
        StagePermission.objects.bulk_create([
            StagePermission(stage=self.stages['applicant_applied'], role=self.roles['licensee'], can_process=True),
            StagePermission(stage=self.stages['level_1'], role=self.roles['level_1'], can_process=True),
            StagePermission(stage=self.stages['level_2'], role=self.roles['level_2'], can_process=True),
            StagePermission(stage=self.stages['level_3'], role=self.roles['level_3'], can_process=True),
            StagePermission(stage=self.stages['level_1_objection'], role=self.roles['licensee'], can_process=True),
        ])
        
        # Create WorkflowTransitions
        WorkflowTransition.objects.bulk_create([
            WorkflowTransition(
                workflow=self.workflow,
                from_stage=self.stages['applicant_applied'],
                to_stage=self.stages['level_1'],
                condition={}
            ),
            WorkflowTransition(
                workflow=self.workflow,
                from_stage=self.stages['level_1'],
                to_stage=self.stages['level_2'],
                condition={}
            ),
            WorkflowTransition(
                workflow=self.workflow,
                from_stage=self.stages['level_1'],
                to_stage=self.stages['level_1_objection'],
                condition={'has_objections': True}
            ),
            WorkflowTransition(
                workflow=self.workflow,
                from_stage=self.stages['level_1_objection'],
                to_stage=self.stages['applicant_applied'],
                condition={}
            ),
            WorkflowTransition(
                workflow=self.workflow,
                from_stage=self.stages['applicant_applied'],
                to_stage=self.stages['level_1'],
                condition={'objections_resolved': True}
            ),
            WorkflowTransition(
                workflow=self.workflow,
                from_stage=self.stages['level_3'],
                to_stage=self.stages['level_2'],
                condition={'needs_reinspection': True}
            ),
        ])
        
        # Create test application
        self.application = LicenseApplication.objects.create(
            application_id='TEST123',
            workflow=self.workflow,
            current_stage=self.stages['level_1'],
            excise_district_id=1,  # Adjust based on your District model
            license_category_id=1,  # Adjust based on your LicenseCategory model
            excise_subdivision_id=1,
            license_type_id=1,
            establishment_name='Test Bar',
            mobile_number=1234567890,
            email='test@example.com',
            license_nature='Retail',
            functioning_status='Operational',
            mode_of_operation='Manual',
            site_subdivision_id=1,
            police_station_id=1,
            location_category='Urban',
            location_name='Test Location',
            ward_name='Ward 1',
            business_address='123 Test Street',
            road_name='Main Road',
            pin_code=123456
        )

    def test_advance_level_1_to_level_2(self):
        self.client.force_authenticate(user=self.users['level_1'])
        url = reverse('advance-license-application', kwargs={
            'application_id': self.application.application_id,
            'stage_id': self.stages['level_2'].id
        })
        response = self.client.post(url, {'context_data': {}}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.application.refresh_from_db()
        self.assertEqual(self.application.current_stage, self.stages['level_2'])

    def test_advance_level_1_to_objection(self):
        self.client.force_authenticate(user=self.users['level_1'])
        url = reverse('advance-license-application', kwargs={
            'application_id': self.application.application_id,
            'stage_id': self.stages['level_1_objection'].id
        })
        response = self.client.post(url, {'context_data': {'has_objections': True}}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.application.refresh_from_db()
        self.assertEqual(self.application.current_stage, self.stages['level_1_objection'])

    def test_revert_level_3_to_level_2(self):
        self.application.current_stage = self.stages['level_3']
        self.application.save()
        self.client.force_authenticate(user=self.users['level_3'])
        url = reverse('advance-license-application', kwargs={
            'application_id': self.application.application_id,
            'stage_id': self.stages['level_2'].id
        })
        response = self.client.post(url, {'context_data': {'needs_reinspection': True}}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.application.refresh_from_db()
        self.assertEqual(self.application.current_stage, self.stages['level_2'])

    def test_unauthorized_role(self):
        self.client.force_authenticate(user=self.users['licensee'])
        url = reverse('advance-license-application', kwargs={
            'application_id': self.application.application_id,
            'stage_id': self.stages['level_2'].id
        })
        response = self.client.post(url, {'context_data': {}}, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)