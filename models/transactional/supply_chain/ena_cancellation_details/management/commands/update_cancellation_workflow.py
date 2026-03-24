from django.core.management.base import BaseCommand
from django.db import transaction
from auth.workflow.models import Workflow, WorkflowStage, WorkflowTransition
from models.transactional.supply_chain.ena_cancellation_details.models import EnaCancellationDetail

class Command(BaseCommand):
    help = 'Updates ENA Cancellation workflow to an approve-only flow with payslip approval'

    def handle(self, *args, **kwargs):
        with transaction.atomic():
            workflow_name = 'ENA Cancellation'
            workflow, created = Workflow.objects.get_or_create(name=workflow_name)
            
            if created:
                self.stdout.write(self.style.SUCCESS(f"Created new workflow: {workflow_name}"))
            else:
                self.stdout.write(self.style.SUCCESS(f"Updating existing workflow: {workflow_name}"))

            # Target flow:
            # ForwardedCancellationToCommissioner -> ApprovedCancellationByCommissioner
            # ApprovedCancellationByCommissioner -> ForwardedCancellationPaySLipToCommissioner
            # ForwardedCancellationPaySLipToCommissioner -> ApprovedCancellationPaySLipByCommissioner

            stage_names_map = {
                'ForwardedCancellationToCommissioner': 'ForwardedCancellationToCommissioner',
                'ApprovedCancellationByCommissioner': 'ApprovedCancellationByCommissioner',
                'ForwardedCancellationPaySLipToCommissioner': 'ForwardedCancellationPaySLipToCommissioner',
                'ApprovedCancellationPaySlipByCommissioner': 'ApprovedCancellationPaySLipByCommissioner',  # Note SLip
            }
            rejected_stage_names = [
                'RejectedCancellationByCommissioner',
                'RejectedCancellationPaySlipByCommissioner',
            ]

            stage_objects = {}
            for key, db_name in stage_names_map.items():
                try:
                    stage = WorkflowStage.objects.get(workflow=workflow, name=db_name)
                    stage_objects[key] = stage
                    self.stdout.write(f"Found existing stage: {db_name}")
                except WorkflowStage.DoesNotExist:
                     self.stdout.write(self.style.WARNING(f"Stage not found: {db_name}, creating..."))
                     stage = WorkflowStage.objects.create(workflow=workflow, name=db_name)
                     stage_objects[key] = stage

            # Remove all transitions for this workflow, then recreate only the desired minimal set.
            WorkflowTransition.objects.filter(workflow=workflow).delete()
            self.stdout.write("Cleared old transitions.")

            # Define Transitions
            transitions = [
                # Initial Cancellation Approval
                {
                    'from': 'ForwardedCancellationToCommissioner',
                    'to': 'ApprovedCancellationByCommissioner',
                    'condition': {'role': 'commissioner', 'action': 'Approve'},
                },
                # Payslip Submission (Licensee uploads payslip after approval)
                {
                    'from': 'ApprovedCancellationByCommissioner',
                    'to': 'ForwardedCancellationPaySLipToCommissioner',
                    'condition': {'role': 'licensee', 'action': 'SubmitPayslip'},
                },
                # Payslip Approval
                {
                    'from': 'ForwardedCancellationPaySLipToCommissioner',
                    'to': 'ApprovedCancellationPaySlipByCommissioner',
                    'condition': {'role': 'commissioner', 'action': 'ApprovePayslip'},
                }
            ]

            for t in transitions:
                from_stage = stage_objects[t['from']]
                to_stage = stage_objects[t['to']]
                WorkflowTransition.objects.create(
                    workflow=workflow,
                    from_stage=from_stage,
                    to_stage=to_stage,
                    condition=t['condition']
                )
                self.stdout.write(f"Created transition: {t['from']} -> {t['to']} ({t['condition']['action']})")

            # Attempt to remove rejected stages if they are no longer referenced by cancellation records.
            for rejected_name in rejected_stage_names:
                rejected_stage = WorkflowStage.objects.filter(workflow=workflow, name=rejected_name).first()
                if not rejected_stage:
                    continue

                in_use = EnaCancellationDetail.objects.filter(current_stage=rejected_stage).exists()
                if in_use:
                    self.stdout.write(
                        self.style.WARNING(
                            f"Rejected stage '{rejected_name}' is still referenced by cancellation data; keeping stage."
                        )
                    )
                    continue

                rejected_stage.delete()
                self.stdout.write(self.style.SUCCESS(f"Deleted unused rejected stage: {rejected_name}"))

            self.stdout.write(self.style.SUCCESS("Successfully updated ENA Cancellation workflow (clean approve-only flow)."))
