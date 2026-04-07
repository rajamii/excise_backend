from django.core.management.base import BaseCommand
from auth.workflow.models import Workflow, WorkflowStage, WorkflowTransition, StagePermission
from auth.workflow.constants import WORKFLOW_IDS
from auth.roles.models import Role

class Command(BaseCommand):
    help = 'Populates Workflow tables for Transit Permit'

    @staticmethod
    def _normalize_role_token(role_name):
        token = ''.join(ch for ch in str(role_name or '').lower() if ch.isalnum())
        if token in {'officerincharge', 'officercharge', 'oic', 'offcierincharge'}:
            return 'officer'
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
        deleted = 0
        for transition in WorkflowTransition.objects.filter(workflow=workflow):
            pair = (transition.from_stage_id, transition.to_stage_id)
            cond = transition.condition or {}
            action = str(cond.get('action') or '').strip().lower()
            if action == 'view' or pair not in required_pairs:
                transition.delete()
                deleted += 1
        return deleted

    def handle(self, *args, **kwargs):
        self.stdout.write("Starting Transit Permit Workflow Population...")
        role_id_map = self._build_role_id_map()

        # 1. Ensure Workflow exists
        workflow_name = "Transit Permit"
        workflow, created = Workflow.objects.get_or_create(
            id=WORKFLOW_IDS['TRANSIT_PERMIT'],
            defaults={"description": "Workflow for Transit Permit Application and Approval"}
        )
        if created:
            self.stdout.write(f"Created Workflow: {workflow_name}")
        else:
            self.stdout.write(f"Workflow {workflow_name} already exists.")

        # 2. Define Stages
        # Mapping: Name -> (Description, IsInitial, IsFinal)
        # NOTE: Historically the "Pending Review" stage was named
        # "PaymentSuccessfulandForwardedToOfficerincharge". We keep a clear stage label so
        # users understand payment is done and OIC approval is pending.
        pending_stage_name = "Payment Successful, Pending OIC Approval"
        stages_data = {
            "Ready for Payment": ("Application submitted, pending payment", True, False),
            pending_stage_name: ("Payment successful and forwarded. Pending Officer In-Charge approval.", False, False),
            "TransitPermitSuccessfullyApproved": ("Approved by Officer", False, True),
            "Cancelled by Officer In-Charge - Refund Initiated Successfully": ("Rejected by Officer, refund initiated", False, True),
        }

        stage_objects = {}
        for name, (desc, is_init, is_final) in stages_data.items():
            # Backward-compat: if an older stage name exists, rename it in-place to keep ids stable.
            lookup_names = [name]
            if name == pending_stage_name:
                lookup_names = [
                    pending_stage_name,
                    "Pending",
                    "PaymentSuccessfulandForwardedToOfficerincharge",
                    "Payment Successful",
                ]

            stage = (
                WorkflowStage.objects.filter(workflow=workflow, name__in=lookup_names)
                .order_by("id")
                .first()
            )
            created = False
            if not stage:
                stage = WorkflowStage.objects.create(
                    workflow=workflow,
                    name=name,
                    description=desc,
                    is_initial=is_init,
                    is_final=is_final,
                )
                created = True
            else:
                update_fields = []
                if stage.name != name:
                    stage.name = name
                    update_fields.append("name")
                if (stage.description or "") != desc:
                    stage.description = desc
                    update_fields.append("description")
                if bool(stage.is_initial) != bool(is_init):
                    stage.is_initial = is_init
                    update_fields.append("is_initial")
                if bool(stage.is_final) != bool(is_final):
                    stage.is_final = is_final
                    update_fields.append("is_final")
                if update_fields:
                    stage.save(update_fields=update_fields)

            stage_objects[name] = stage
            if created:
                self.stdout.write(f"Created Stage: {name}")

        # 3. Define Transitions
        # (FromStage, ToStage, ConditionDict)
        transitions_data = [
            (
                "Ready for Payment",
                pending_stage_name,
                "licensee",
                "PAY"
            ),
            (
                pending_stage_name,
                "TransitPermitSuccessfullyApproved",
                "officer",
                "APPROVE"
            ),
             (
                pending_stage_name,
                "Cancelled by Officer In-Charge - Refund Initiated Successfully",
                "officer",
                "REJECT"
            ),
        ]

        required_pairs = set()
        for from_name, to_name, role_name, action_name in transitions_data:
            from_stage = stage_objects[from_name]
            to_stage = stage_objects[to_name]
            condition = {"action": action_name, "role": role_name}
            role_id = role_id_map.get(role_name)
            if role_id is not None:
                condition["role_id"] = role_id

            self._upsert_transition(workflow, from_stage, to_stage, condition)
            required_pairs.add((from_stage.id, to_stage.id))
            self.stdout.write(f"Created/Updated Transition: {from_name} -> {to_name} ({condition})")

        deleted = self._cleanup_transitions(workflow, required_pairs)
        if deleted:
            self.stdout.write(self.style.WARNING(f"Removed {deleted} obsolete transitions from Transit Permit workflow"))

        # 4. Define Stage Permissions
        # (StageName, RoleName, CanProcess)
        # Note: In a real app, Role Name should match exact DB role names. 
        # Here we assume 'licensee' and 'officer' exist or are placeholders.
        permissions_data = [
            ("Ready for Payment", "licensee", True),
            (pending_stage_name, "officer", True),
            ("TransitPermitSuccessfullyApproved", "officer", True), 
        ]

        for stage_name, role_name, can_process in permissions_data:
            stage = stage_objects[stage_name]
            role, created = Role.objects.get_or_create(name=role_name) 
            
            if not StagePermission.objects.filter(stage=stage, role=role).exists():
                StagePermission.objects.create(
                    stage=stage,
                    role=role,
                    can_process=can_process
                )
                self.stdout.write(f"Created Permission: {stage_name} -> {role_name}")
            else:
                 self.stdout.write(f"Permission already exists: {stage_name} -> {role_name}")

        self.stdout.write(self.style.SUCCESS("Successfully populated Transit Permit Workflow."))
