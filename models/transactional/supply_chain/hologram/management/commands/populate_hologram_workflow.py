from django.core.management.base import BaseCommand
from auth.workflow.models import Workflow, WorkflowStage, WorkflowTransition, Role

class Command(BaseCommand):
    help = 'Populates the database with initial Hologram workflows, stages, and transitions'

    def handle(self, *args, **options):
        # 1. Hologram Procurement Workflow
        proc_workflow, created = Workflow.objects.get_or_create(
            name='Hologram Procurement',
            defaults={'description': 'Workflow for procuring hologram rolls from printing press'}
        )
        if created:
            self.stdout.write(self.style.SUCCESS('Created Workflow: Hologram Procurement'))
        else:
            self.stdout.write('Workflow "Hologram Procurement" already exists')

        # Stages
        proc_stages_data = [
            {'name': 'Submitted', 'is_initial': True, 'is_final': False},
            {'name': 'Under IT Cell Review', 'is_initial': False, 'is_final': False},
            {'name': 'Forwarded to Commissioner', 'is_initial': False, 'is_final': False},
            {'name': 'Approved by Commissioner', 'is_initial': False, 'is_final': False},
            {'name': 'Rejected by Commissioner', 'is_initial': False, 'is_final': True}, # Can be final
            {'name': 'Payment Completed', 'is_initial': False, 'is_final': False},
            {'name': 'Cartoon Assigned', 'is_initial': False, 'is_final': True},
        ]

        proc_stages = {}
        for stage_data in proc_stages_data:
            stage, created = WorkflowStage.objects.get_or_create(
                workflow=proc_workflow,
                name=stage_data['name'],
                defaults={
                    'is_initial': stage_data['is_initial'],
                    'is_final': stage_data['is_final']
                }
            )
            proc_stages[stage.name] = stage
            if created:
                self.stdout.write(f"  - Created Stage: {stage.name}")

        # Transitions with conditions (Role and Action)
        # Condition format: {'role': '<role_name>', 'action': '<action_name>'}
        proc_transitions = [
            ('Submitted', 'Under IT Cell Review', {'role': 'it_cell', 'action': 'verify'}),
            ('Under IT Cell Review', 'Forwarded to Commissioner', {'role': 'it_cell', 'action': 'forward'}), # Or 'verify' again?
            ('Forwarded to Commissioner', 'Approved by Commissioner', {'role': 'commissioner', 'action': 'approve'}),
            ('Forwarded to Commissioner', 'Rejected by Commissioner', {'role': 'commissioner', 'action': 'reject'}),
            ('Approved by Commissioner', 'Payment Completed', {'role': 'licensee', 'action': 'pay'}), # Auto or Manual
            ('Payment Completed', 'Cartoon Assigned', {'role': 'officer_in_charge', 'action': 'assign_cartons'}),
        ]

        for from_name, to_name, condition in proc_transitions:
            from_stage = proc_stages.get(from_name)
            to_stage = proc_stages.get(to_name)
            if from_stage and to_stage:
                WorkflowTransition.objects.update_or_create(
                    workflow=proc_workflow,
                    from_stage=from_stage,
                    to_stage=to_stage,
                    defaults={'condition': condition}
                )
                self.stdout.write(f"  - Created/Updated Transition: {from_name} -> {to_name} ({condition})")


        # 2. Hologram Request Workflow
        req_workflow, created = Workflow.objects.get_or_create(
            name='Hologram Request',
            defaults={'description': 'Workflow for requesting hologram usage for bottling'}
        )
        if created:
            self.stdout.write(self.style.SUCCESS('\nCreated Workflow: Hologram Request'))

        # Stages
        req_stages_data = [
            {'name': 'Submitted', 'is_initial': True, 'is_final': False},
            {'name': 'Approved by Permit Section', 'is_initial': False, 'is_final': False},
            {'name': 'Rejected by Permit Section', 'is_initial': False, 'is_final': True},
            {'name': 'Rejected by Permit Section', 'is_initial': False, 'is_final': True},
            {'name': 'In Use', 'is_initial': False, 'is_final': False}, # OIC Issues -> In Use
            {'name': 'Production Completed', 'is_initial': False, 'is_final': True}, # Daily Register -> Completed
        ]

        req_stages = {}
        for stage_data in req_stages_data:
            stage, created = WorkflowStage.objects.get_or_create(
                workflow=req_workflow,
                name=stage_data['name'],
                defaults={
                    'is_initial': stage_data['is_initial'],
                    'is_final': stage_data['is_final']
                }
            )
            req_stages[stage.name] = stage
            if created:
                self.stdout.write(f"  - Created Stage: {stage.name}")

        # Transitions
        req_transitions = [
            ('Submitted', 'Approved by Permit Section', {'role': 'permit-section', 'action': 'approve'}),
            ('Submitted', 'Rejected by Permit Section', {'role': 'permit-section', 'action': 'reject'}),
            ('Approved by Permit Section', 'In Use', {'role': 'officer_in_charge', 'action': 'issue'}), 
            ('Submitted', 'In Use', {'role': 'officer_in_charge', 'action': 'issue'}), # Self-Service Issue
            ('In Use', 'Production Completed', {'role': 'officer_in_charge', 'action': 'complete'}), # Finalize
            ('In Use', 'Production Completed', {'role': 'licensee', 'action': 'complete'}), # Finalize via Daily Entry
        ]

        for from_name, to_name, condition in req_transitions:
            from_stage = req_stages.get(from_name)
            to_stage = req_stages.get(to_name)
            if from_stage and to_stage:
                WorkflowTransition.objects.update_or_create(
                    workflow=req_workflow,
                    from_stage=from_stage,
                    to_stage=to_stage,
                    defaults={'condition': condition}
                )
                self.stdout.write(f"  - Created/Updated Transition: {from_name} -> {to_name} ({condition})")

        self.stdout.write(self.style.SUCCESS('\nWorkflow population completed successfully.'))
