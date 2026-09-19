from django.core.management.base import BaseCommand
from django.db import transaction
from auth.workflow.models import Workflow, WorkflowStage, WorkflowTransition
from auth.workflow.constants import WORKFLOW_IDS
from auth.roles.models import Role


class Command(BaseCommand):
    help = 'Populates Workflow, Stages, and Transitions for ENA Bulk Spirit Usage'

    def handle(self, *args, **kwargs):
        self.stdout.write('Starting ENA Bulk Spirit Usage workflow population...')

        try:
            with transaction.atomic():
                workflow_id = WORKFLOW_IDS.get('ENA_BULK_SPIRIT_USAGE', 18)
                workflow, created = Workflow.objects.get_or_create(
                    id=workflow_id,
                    defaults={
                        'name': 'ENA Bulk Spirit Usage',
                        'description': 'Workflow for ENA Bulk Spirit Usage requests from Licensee to OIC'
                    }
                )
                if created:
                    self.stdout.write(f'Created Workflow: {workflow.name} (id={workflow.id})')
                else:
                    self.stdout.write(f'Using existing Workflow: {workflow.name} (id={workflow.id})')

                # Stages:
                # 1. Pending OIC Approval
                stage_pending, _ = WorkflowStage.objects.get_or_create(
                    workflow=workflow,
                    name='Pending OIC Approval',
                    defaults={
                        'description': 'Submitted by Licensee and awaiting Officer-In-Charge approval',
                        'is_initial': True,
                        'is_final': False,
                        'order': 1
                    }
                )

                # 2. Approved
                stage_approved, _ = WorkflowStage.objects.get_or_create(
                    workflow=workflow,
                    name='Approved',
                    defaults={
                        'description': 'Approved by Officer-In-Charge',
                        'is_initial': False,
                        'is_final': True,
                        'order': 2
                    }
                )

                # 3. Rejected
                stage_rejected, _ = WorkflowStage.objects.get_or_create(
                    workflow=workflow,
                    name='Rejected',
                    defaults={
                        'description': 'Rejected by Officer-In-Charge',
                        'is_initial': False,
                        'is_final': True,
                        'order': 3
                    }
                )

                # OIC Role lookup
                oic_role = Role.objects.filter(name__icontains='officer').first()
                oic_role_name = oic_role.name if oic_role else 'Officer-In-Charge'
                oic_role_id = oic_role.id if oic_role else 5

                # Transitions
                # APPROVE
                t_approve, _ = WorkflowTransition.objects.get_or_create(
                    workflow=workflow,
                    from_stage=stage_pending,
                    to_stage=stage_approved,
                    defaults={
                        'condition': {
                            'role': oic_role_name,
                            'role_id': oic_role_id,
                            'action': 'APPROVE'
                        }
                    }
                )
                # REJECT
                t_reject, _ = WorkflowTransition.objects.get_or_create(
                    workflow=workflow,
                    from_stage=stage_pending,
                    to_stage=stage_rejected,
                    defaults={
                        'condition': {
                            'role': oic_role_name,
                            'role_id': oic_role_id,
                            'action': 'REJECT'
                        }
                    }
                )

                self.stdout.write(self.style.SUCCESS('ENA Bulk Spirit Usage workflow populated successfully!'))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error: {str(e)}'))
