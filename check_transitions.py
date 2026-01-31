import os
import django
import sys

sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'excise_backend.settings')
django.setup()

from auth.workflow.models import Workflow, WorkflowTransition, WorkflowStage

try:
    wf = Workflow.objects.get(name='ENA Cancellation')
    # Find the stage 'ForwardedCancellationPaySLipToCommissioner'
    stage = WorkflowStage.objects.filter(workflow=wf, name__iexact='ForwardedCancellationPaySLipToCommissioner').first()
    
    if stage:
        print(f"Stage Found: {stage.name} (ID: {stage.id})")
        transitions = WorkflowTransition.objects.filter(workflow=wf, from_stage=stage)
        print(f"Found {transitions.count()} transitions.")
        for t in transitions:
            print(f"TRA: {t.from_stage.name[:20]} -> {t.to_stage.name[:20]}")
            print(f"   ACT: '{t.condition.get('action')}'")
            print(f"   ROLE: '{t.condition.get('role')}'")
            print("---")
    else:
        print("Stage 'ApprovedCancellationByCommissioner' not found.")

except Exception as e:
    print(f"Error: {e}")
