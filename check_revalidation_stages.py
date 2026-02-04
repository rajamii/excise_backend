
import os
import django
import sys

# Setup Django environment
sys.path.append(r'c:\Users\TG_Namgyal\Desktop\FINAL_31st_2026\excise_backend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'excise_backend.settings')
django.setup()

from auth.workflow.models import Workflow, WorkflowStage, WorkflowTransition

try:
    workflow = Workflow.objects.get(id=4)
    with open('stages_dump.txt', 'w') as f:
        f.write(f"Workflow: {workflow.name} (ID: 4)\n")
        
        stages = WorkflowStage.objects.filter(workflow=workflow).order_by('id')
        f.write("\nStages:\n")
        for stage in stages:
            f.write(f"ID: {stage.id}, Name: {stage.name}, Initial: {stage.is_initial}, Final: {stage.is_final}\n")
            
        transitions = WorkflowTransition.objects.filter(workflow=workflow)
        f.write("\nTransitions:\n")
        for t in transitions:
            f.write(f"{t.from_stage.name} -> {t.to_stage.name} (Condition: {t.condition})\n")

except Workflow.DoesNotExist:
    print("Workflow ID 4 not found.")
