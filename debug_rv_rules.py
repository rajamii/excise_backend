import os
import django
from django.conf import settings

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'excise_backend.settings')
django.setup()

from models.masters.supply_chain.status_master.models import WorkflowRule, StatusMaster

def check_revalidation_rules():
    print("Checking Revalidation Workflow Rules...")
    
    # Statuses of interest
    # RV_17: ForwardedRevalidationToCommissioner
    # RV_01: ApprovedRevalidationByCommissioner
    # RV_02: RejectedRevalidationByCommissioner
    
    status_codes = ['RV_17', 'RV_01', 'RV_02']
    
    for code in status_codes:
        print(f"\n--- Checking Rules for Status: {code} ---")
        try:
            status = StatusMaster.objects.get(status_code=code)
            print(f"Status Name: {status.status_name}")
            
            rules = WorkflowRule.objects.filter(current_status=status)
            if not rules.exists():
                print("No rules found.")
            
            for rule in rules:
                print(f"Rule: Role={rule.allowed_role}, Action={rule.action} -> Next={rule.next_status.status_code} ({rule.next_status.status_name})")
                
        except StatusMaster.DoesNotExist:
            print(f"Status {code} not found in DB.")

if __name__ == '__main__':
    check_revalidation_rules()
