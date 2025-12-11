import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'excise_backend.settings')
django.setup()

from models.masters.supply_chain.status_master.models import WorkflowRule, StatusMaster

def verify_revalidation_rules():
    """Verify revalidation workflow rules in the database."""
    print("\n" + "="*80)
    print("REVALIDATION WORKFLOW RULES VERIFICATION")
    print("="*80 + "\n")
    
    rv_rules = WorkflowRule.objects.filter(
        current_status__status_code__startswith='RV'
    ).select_related('current_status', 'next_status').order_by('current_status__status_code', 'action')
    
    if rv_rules.exists():
        print(f"Found {rv_rules.count()} revalidation workflow rules:\n")
        for rule in rv_rules:
            print(f"  {rule.current_status.status_code} ({rule.current_status.status_name})")
            print(f"    + {rule.action} by {rule.allowed_role}")
            print(f"    → {rule.next_status.status_code} ({rule.next_status.status_name})")
            print()
    else:
        print("❌ No revalidation workflow rules found!")
    
    print("="*80 + "\n")

if __name__ == '__main__':
    verify_revalidation_rules()
