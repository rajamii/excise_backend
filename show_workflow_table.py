import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'excise_backend.settings')
django.setup()

from models.masters.supply_chain.status_master.models import WorkflowRule, StatusMaster

def show_workflow_table():
    """Display the workflow_rules table contents."""
    print("\n" + "="*120)
    print("WORKFLOW_RULES TABLE CONTENTS")
    print("="*120 + "\n")
    
    rules = WorkflowRule.objects.all().select_related('current_status', 'next_status').order_by('id')
    
    print(f"{'ID':<5} {'Current Status':<35} {'Action':<10} {'Role':<20} {'Next Status':<35}")
    print("-" * 120)
    
    for rule in rules:
        print(f"{rule.id:<5} {rule.current_status.status_name:<35} {rule.action:<10} {rule.allowed_role:<20} {rule.next_status.status_name:<35}")
    
    print("\n" + "="*120)
    print(f"Total rows in workflow_rules table: {rules.count()}")
    print("="*120 + "\n")

if __name__ == '__main__':
    show_workflow_table()
