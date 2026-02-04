
import os
import django
import sys
import json

# Setup Django environment
sys.path.append(r'c:\Users\TG_Namgyal\Desktop\FINAL_31st_2026\excise_backend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'excise_backend.settings')
django.setup()

from auth.workflow.models import Workflow, WorkflowStage, WorkflowTransition

def update_transitions():
    try:
        workflow = Workflow.objects.get(id=4)
        print(f"Updating transitions for Workflow: {workflow.name}")
        
        # Get Stages
        try:
            forwarded_stage = WorkflowStage.objects.get(workflow=workflow, name='ForwardedRevalidationToCommissioner')
            approved_stage = WorkflowStage.objects.get(workflow=workflow, name='ApprovedRevalidationByCommissioner')
            rejected_stage = WorkflowStage.objects.get(workflow=workflow, name='RejectedRevalidationByCommissioner')
            invalid_stage = WorkflowStage.objects.get(workflow=workflow, name='IMPORT PERMIT EXTENDS 45 DAYS - INVALID')
        except WorkflowStage.DoesNotExist as e:
            print(f"Error finding stage: {e}")
            return

        # 1. ForwardedRevalidationToCommissioner -> ApprovedRevalidationByCommissioner (Role: commissioner)
        t1, created1 = WorkflowTransition.objects.update_or_create(
            workflow=workflow,
            from_stage=forwarded_stage,
            to_stage=approved_stage,
            defaults={
                'condition': {'role': 'commissioner', 'action': 'APPROVE'}
            }
        )
        print(f"Transition 1 Updated: {t1.from_stage.name} -> {t1.to_stage.name} (Action: APPROVE, Role: commissioner)")

        # 2. ForwardedRevalidationToCommissioner -> RejectedRevalidationByCommissioner (Role: commissioner)
        t2, created2 = WorkflowTransition.objects.update_or_create(
            workflow=workflow,
            from_stage=forwarded_stage,
            to_stage=rejected_stage,
            defaults={
                'condition': {'role': 'commissioner', 'action': 'REJECT'}
            }
        )
        print(f"Transition 2 Updated: {t2.from_stage.name} -> {t2.to_stage.name} (Action: REJECT, Role: commissioner)")
        
        # 3. [REMOVED PER USER REQUEST] IMPORT PERMIT EXTENDS... -> Commissioner actions
        # We need to ensure these do NOT exist.
        WorkflowTransition.objects.filter(
            workflow=workflow,
            from_stage=invalid_stage,
            condition__contains={'role': 'commissioner'}
        ).delete()
        print(f"Removed transitions for {invalid_stage.name} (Role: commissioner)")

        # Cleanup: Remove transitions from RevalidationPending if we want (Optional but good for cleanliness)
        # Getting RevalidationPending if exists
        try:
             pending_stage = WorkflowStage.objects.get(workflow=workflow, name='RevalidationPending')
             # Note: We are not deleting the stage itself, just potentially old transitions if they confuse things.
             # But user instructions didn't explicitly ask to delete old ones, just ensure new flow works.
             # I'll leave them for now to be safe, or just ensure no conflicting transitions exist.
             pass
        except:
             pass

    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == '__main__':
    update_transitions()
