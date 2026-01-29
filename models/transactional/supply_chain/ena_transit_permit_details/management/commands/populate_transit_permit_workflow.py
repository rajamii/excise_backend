from django.core.management.base import BaseCommand
from auth.workflow.models import Workflow, WorkflowStage, WorkflowTransition, StagePermission
from auth.roles.models import Role
import logging

class Command(BaseCommand):
    help = 'Populates Workflow tables for Transit Permit'

    def handle(self, *args, **kwargs):
        self.stdout.write("Starting Transit Permit Workflow Population...")

        # 1. Ensure Workflow exists
        workflow_name = "Transit Permit"
        workflow, created = Workflow.objects.get_or_create(
            name=workflow_name,
            defaults={"description": "Workflow for Transit Permit Application and Approval"}
        )
        if created:
            self.stdout.write(f"Created Workflow: {workflow_name}")
        else:
            self.stdout.write(f"Workflow {workflow_name} already exists.")

        # 2. Define Stages
        # Mapping: Name -> (Description, IsInitial, IsFinal)
        stages_data = {
            "Ready for Payment": ("Application submitted, pending payment", True, False),
            "PaymentSuccessfulandForwardedToOfficerincharge": ("Payment successful, forwarded to Officer", False, False),
            "TransitPermitSucessfulyApproved": ("Approved by Officer", False, True),
            "Cancelled by Officer In-Charge - Refund Initiated Successfully": ("Rejected by Officer, refund initiated", False, True),
        }

        stage_objects = {}
        for name, (desc, is_init, is_final) in stages_data.items():
            stage, created = WorkflowStage.objects.get_or_create(
                workflow=workflow,
                name=name,
                defaults={
                    "description": desc,
                    "is_initial": is_init,
                    "is_final": is_final
                }
            )
            stage_objects[name] = stage
            if created:
                self.stdout.write(f"Created Stage: {name}")

        # 3. Define Transitions
        # (FromStage, ToStage, ConditionDict)
        transitions_data = [
            (
                "Ready for Payment",
                "PaymentSuccessfulandForwardedToOfficerincharge",
                {"action": "PAY", "role": "licensee"} # Or "user"? Assuming licensee based on context
            ),
            (
                "PaymentSuccessfulandForwardedToOfficerincharge",
                "TransitPermitSucessfulyApproved",
                {"action": "APPROVE", "role": "officer"} # Need to verify exact role name later, using generic 'officer' for now or update logic to match
            ),
             (
                "PaymentSuccessfulandForwardedToOfficerincharge",
                "Cancelled by Officer In-Charge - Refund Initiated Successfully",
                {"action": "REJECT", "role": "officer"}
            ),
        ]

        for from_name, to_name, condition in transitions_data:
            from_stage = stage_objects[from_name]
            to_stage = stage_objects[to_name]
            
            # Check if transition exists to avoid duplicates
            if not WorkflowTransition.objects.filter(
                workflow=workflow,
                from_stage=from_stage,
                to_stage=to_stage,
                condition=condition
            ).exists():
                WorkflowTransition.objects.create(
                    workflow=workflow,
                    from_stage=from_stage,
                    to_stage=to_stage,
                    condition=condition
                )
                self.stdout.write(f"Created Transition: {from_name} -> {to_name}")
            else:
                self.stdout.write(f"Transition already exists: {from_name} -> {to_name}")

        # 4. Define Stage Permissions
        # (StageName, RoleName, CanProcess)
        # Note: In a real app, Role Name should match exact DB role names. 
        # Here we assume 'licensee' and 'officer' exist or are placeholders.
        permissions_data = [
            ("Ready for Payment", "licensee", True),
            ("PaymentSuccessfulandForwardedToOfficerincharge", "officer", True),
            ("TransitPermitSucessfulyApproved", "officer", True), 
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
