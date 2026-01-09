from django.core.management.base import BaseCommand
from django.db import transaction
from auth.workflow.models import Workflow, WorkflowStage, WorkflowTransition
from models.masters.supply_chain.status_master.models import StatusMaster, WorkflowRule

class Command(BaseCommand):
    help = 'Populates Workflow tables from existing StatusMaster and WorkflowRule for Supply Chain'

    def handle(self, *args, **kwargs):
        self.stdout.write("Starting workflow population...")

        try:
            with transaction.atomic():
                # 1. Create Workflow
                workflow, created = Workflow.objects.get_or_create(
                    name="Supply Chain",
                    defaults={"description": "Workflow for ENA Requisition and Supply Chain"}
                )
                if created:
                    self.stdout.write(f"Created Workflow: {workflow.name}")
                else:
                    self.stdout.write(f"Using existing Workflow: {workflow.name}")

                # 2. Create Stages from StatusMaster (RQ_*)
                # Assuming RQ_ prefix is for Requisition.
                statuses = StatusMaster.objects.filter(status_code__startswith='RQ_')
                
                status_stage_map = {} # Map status_id to WorkflowStage

                for status_obj in statuses:
                    is_initial = (status_obj.status_code == 'RQ_00')
                    # Determine is_final. 'RQ_09' is Approved, 'RQ_10' is Rejected.
                    # You might need to adjust this logic based on your specific requirements.
                    # For now, let's assume RQ_09 (Approved) and RQ_10 (Rejected) are final.
                    is_final = status_obj.status_code in ['RQ_09', 'RQ_10']

                    stage, stage_created = WorkflowStage.objects.get_or_create(
                        workflow=workflow,
                        name=status_obj.status_name,
                        defaults={
                            "description": status_obj.status_name,
                            "is_initial": is_initial,
                            "is_final": is_final
                        }
                    )
                    status_stage_map[status_obj.status_id] = stage
                    if stage_created:
                        self.stdout.write(f"Created Stage: {stage.name}")

                # 3. Create Transitions from WorkflowRule
                # We need to map WorkflowRule (which links StatusMaster) to WorkflowTransition (which links WorkflowStage)
                
                rules = WorkflowRule.objects.filter(current_status__status_code__startswith='RQ_')
                
                for rule in rules:
                    from_stage = status_stage_map.get(rule.current_status_id)
                    to_stage = status_stage_map.get(rule.next_status_id)

                    if from_stage and to_stage:
                        # Store role and action in condition
                        condition = {
                            "role": rule.allowed_role,
                            "action": rule.action
                        }
                        
                        transition, trans_created = WorkflowTransition.objects.get_or_create(
                            workflow=workflow,
                            from_stage=from_stage,
                            to_stage=to_stage,
                            defaults={
                                "condition": condition
                            }
                        )
                        if trans_created:
                            self.stdout.write(f"Created Transition: {from_stage.name} -> {to_stage.name} ({rule.action} by {rule.allowed_role})")
                    else:
                        self.stdout.write(self.style.WARNING(f"Skipping rule {rule} due to missing stage mapping"))

            self.stdout.write(self.style.SUCCESS("Workflow population completed successfully."))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error: {str(e)}"))
