from django.core.management.base import BaseCommand
from auth.workflow.models import Workflow, WorkflowStage, WorkflowTransition, Role
from auth.workflow.constants import WORKFLOW_IDS

class Command(BaseCommand):
    help = 'Populates the database with initial Hologram workflows, stages, and transitions'

    @staticmethod
    def _normalize_role_token(role_name):
        token = ''.join(ch for ch in str(role_name or '').lower() if ch.isalnum())
        if token in {'officerincharge', 'officercharge', 'oic', 'offcierincharge'}:
            return 'officer_in_charge'
        if token in {'itcell'}:
            return 'it_cell'
        return token

    def _build_role_id_map(self):
        role_id_map = {}
        for role in Role.objects.all().only('id', 'name'):
            canonical = self._normalize_role_token(role.name)
            if canonical:
                role_id_map[canonical] = role.id
        return role_id_map

    def _upsert_transition(self, workflow, from_stage, to_stage, condition):
        pair_qs = WorkflowTransition.objects.filter(
            workflow=workflow,
            from_stage=from_stage,
            to_stage=to_stage
        ).order_by('id')

        existing = pair_qs.first()
        if existing:
            existing.condition = condition
            existing.save(update_fields=['condition'])
            duplicate_ids = list(pair_qs.values_list('id', flat=True))[1:]
            if duplicate_ids:
                WorkflowTransition.objects.filter(id__in=duplicate_ids).delete()
        else:
            WorkflowTransition.objects.create(
                workflow=workflow,
                from_stage=from_stage,
                to_stage=to_stage,
                condition=condition
            )

    def _cleanup_transitions(self, workflow, required_pairs):
        deleted_count = 0
        for transition in WorkflowTransition.objects.filter(workflow=workflow):
            pair = (transition.from_stage_id, transition.to_stage_id)
            cond = transition.condition or {}
            action = str(cond.get('action') or '').strip().lower()

            if action == 'view' or pair not in required_pairs:
                transition.delete()
                deleted_count += 1

        return deleted_count

    def handle(self, *args, **options):
        role_id_map = self._build_role_id_map()

        # 1. Hologram Procurement Workflow
        proc_workflow, created = Workflow.objects.get_or_create(
            id=WORKFLOW_IDS['HOLOGRAM_PROCUREMENT'],
            defaults={
                'name': 'Hologram Procurement',
                'description': 'Workflow for procuring hologram rolls from printing press'
            }
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

        # Transitions with conditions (Role, Role ID, Action)
        proc_transitions = [
            ('Submitted', 'Under IT Cell Review', 'it_cell', 'verify'),
            ('Under IT Cell Review', 'Forwarded to Commissioner', 'it_cell', 'forward'),
            ('Forwarded to Commissioner', 'Approved by Commissioner', 'commissioner', 'approve'),
            ('Forwarded to Commissioner', 'Rejected by Commissioner', 'commissioner', 'reject'),
            ('Approved by Commissioner', 'Payment Completed', 'licensee', 'pay'),
            ('Payment Completed', 'Cartoon Assigned', 'officer_in_charge', 'assign_cartons'),
        ]

        required_proc_pairs = set()
        for from_name, to_name, role_name, action_name in proc_transitions:
            from_stage = proc_stages.get(from_name)
            to_stage = proc_stages.get(to_name)
            if from_stage and to_stage:
                condition = {'role': role_name, 'action': action_name}
                role_id = role_id_map.get(role_name)
                if role_id is not None:
                    condition['role_id'] = role_id

                self._upsert_transition(proc_workflow, from_stage, to_stage, condition)
                required_proc_pairs.add((from_stage.id, to_stage.id))
                self.stdout.write(f"  - Created/Updated Transition: {from_name} -> {to_name} ({condition})")

        deleted_proc = self._cleanup_transitions(proc_workflow, required_proc_pairs)
        if deleted_proc:
            self.stdout.write(self.style.WARNING(f"  - Removed {deleted_proc} obsolete transitions from Hologram Procurement workflow"))

        # 2. Hologram Request Workflow
        req_workflow, created = Workflow.objects.get_or_create(
            id=WORKFLOW_IDS['HOLOGRAM_REQUEST'],
            defaults={
                'name': 'Hologram Request',
                'description': 'Workflow for requesting hologram usage for bottling'
            }
        )
        if created:
            self.stdout.write(self.style.SUCCESS('\nCreated Workflow: Hologram Request'))

        # Stages
        req_stages_data = [
            {'name': 'Submitted', 'is_initial': True, 'is_final': False},
            {'name': 'Approved by OIC', 'is_initial': False, 'is_final': False},
            {'name': 'Rejected by OIC', 'is_initial': False, 'is_final': True},
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

        # Transitions (OIC-direct flow)
        # New flow:
        # Submitted -> In Use (OIC approves/assigns)
        # In Use -> Production Completed (OIC completes)
        req_transitions = [
            # Preferred action name for the new flow
            ('Submitted', 'In Use', 'officer_in_charge', 'approve'),
            # Backward-compatible action name used by older UI payloads
            ('Submitted', 'In Use', 'officer_in_charge', 'issue'),
            # Rejection path (OIC can reject with a reason)
            ('Submitted', 'Rejected by OIC', 'officer_in_charge', 'reject'),
            ('In Use', 'Production Completed', 'officer_in_charge', 'complete'),
        ]

        required_req_pairs = set()
        for from_name, to_name, role_name, action_name in req_transitions:
            from_stage = req_stages.get(from_name)
            to_stage = req_stages.get(to_name)
            if from_stage and to_stage:
                condition = {'role': role_name, 'action': action_name}
                role_id = role_id_map.get(role_name)
                if role_id is not None:
                    condition['role_id'] = role_id

                self._upsert_transition(req_workflow, from_stage, to_stage, condition)
                required_req_pairs.add((from_stage.id, to_stage.id))
                self.stdout.write(f"  - Created/Updated Transition: {from_name} -> {to_name} ({condition})")

        deleted_req = self._cleanup_transitions(req_workflow, required_req_pairs)
        if deleted_req:
            self.stdout.write(self.style.WARNING(f"  - Removed {deleted_req} obsolete transitions from Hologram Request workflow"))

        self.stdout.write(self.style.SUCCESS('\nWorkflow population completed successfully.'))
