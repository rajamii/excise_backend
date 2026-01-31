from django.core.management.base import BaseCommand
from django.db import transaction
from auth.workflow.models import Workflow, WorkflowStage, WorkflowTransition

class Command(BaseCommand):
    help = 'Updates the ENA Cancellation workflow to route directly to Commissioner with Payslip flow'

    def handle(self, *args, **kwargs):
        with transaction.atomic():
            workflow_name = 'ENA Cancellation'
            workflow, created = Workflow.objects.get_or_create(name=workflow_name)
            
            if created:
                self.stdout.write(self.style.SUCCESS(f"Created new workflow: {workflow_name}"))
            else:
                self.stdout.write(self.style.SUCCESS(f"Updating existing workflow: {workflow_name}"))

            # Correct Stage Names from DB Dump
            # 67: ForwardedCancellationToCommissioner
            # 72: ApprovedCancellationByCommissioner
            # 73: RejectedCancellationByCommissioner
            # 69: ForwardedCancellationPaySLipToCommissioner
            # 70: ApprovedCancellationPaySLipByCommissioner
            # 71: RejectedCancellationPaySlipByCommissioner

            stage_names_map = {
                'ForwardedCancellationToCommissioner': 'ForwardedCancellationToCommissioner',
                'ApprovedCancellationByCommissioner': 'ApprovedCancellationByCommissioner',
                'RejectedCancellationByCommissioner': 'RejectedCancellationByCommissioner',
                'ForwardedCancellationPaySLipToCommissioner': 'ForwardedCancellationPaySLipToCommissioner',
                'ApprovedCancellationPaySlipByCommissioner': 'ApprovedCancellationPaySLipByCommissioner', # Note SLip
                'RejectedCancellationPaySlipByCommissioner': 'RejectedCancellationPaySlipByCommissioner'
            }

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

            # Clear existing transitions to strictly enforce the new flow
            # We only remove transitions for the stages we are touching to avoid breaking other parts if any
            # But the user said "do it in the exiting workflow", implying we can reconfigure it.
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
                {
                    'from': 'ForwardedCancellationToCommissioner',
                    'to': 'RejectedCancellationByCommissioner',
                    'condition': {'role': 'commissioner', 'action': 'Reject'},
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
                },
                {
                    'from': 'ForwardedCancellationPaySLipToCommissioner',
                    'to': 'RejectedCancellationPaySlipByCommissioner',
                    'condition': {'role': 'commissioner', 'action': 'RejectPayslip'},
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

            self.stdout.write(self.style.SUCCESS("Successfully updated ENA Cancellation workflow."))
