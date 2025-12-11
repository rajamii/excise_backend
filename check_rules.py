import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'excise_backend.settings')
django.setup()

from models.masters.supply_chain.status_master.models import StatusMaster, WorkflowRule

def check_rv00_rules():
    print("Checking Rules for RV_00 (RevalidationPending)...")
    
    try:
        status_obj = StatusMaster.objects.get(status_code='RV_00')
        print(f"Status Found: {status_obj.status_name} ({status_obj.status_code})")
        
        rules = WorkflowRule.objects.filter(current_status=status_obj)
        print(f"Total Rules for RV_00: {rules.count()}")
        
        approve_rule = rules.filter(action='APPROVE', allowed_role='permit-section').first()
        reject_rule = rules.filter(action='REJECT', allowed_role='permit-section').first()
        
        if approve_rule:
            print(f"✓ APPROVE Rule Found: {approve_rule.current_status.status_code} -> {approve_rule.next_status.status_code}")
        else:
            print("❌ APPROVE Rule MISSING for permit-section")
            
        if reject_rule:
            print(f"✓ REJECT Rule Found: {reject_rule.current_status.status_code} -> {reject_rule.next_status.status_code}")
        else:
            print("❌ REJECT Rule MISSING for permit-section")
            
    except StatusMaster.DoesNotExist:
        print("CRITICAL: RV_00 Status NOT FOUND in StatusMaster!")

    print("\nChecking Rules for RV_18 (INVALID)...")
    try:
        status_obj = StatusMaster.objects.get(status_code='RV_18')
        print(f"Status Found: {status_obj.status_name} ({status_obj.status_code})")
        
        rules = WorkflowRule.objects.filter(current_status=status_obj)
        print(f"Total Rules for RV_18: {rules.count()}")
        
        approve_rule = rules.filter(action='APPROVE', allowed_role='permit-section').first()
        reject_rule = rules.filter(action='REJECT', allowed_role='permit-section').first()
        
        if approve_rule:
            print(f"✓ APPROVE Rule Found: {approve_rule.current_status.status_code} -> {approve_rule.next_status.status_code}")
        else:
            print("❌ APPROVE Rule MISSING for permit-section")
            
        if reject_rule:
            print(f"✓ REJECT Rule Found: {reject_rule.current_status.status_code} -> {reject_rule.next_status.status_code}")
        else:
            print("❌ REJECT Rule MISSING for permit-section")

    except StatusMaster.DoesNotExist:
        print("CRITICAL: RV_18 Status NOT FOUND in StatusMaster!")

if __name__ == '__main__':
    check_rv00_rules()
