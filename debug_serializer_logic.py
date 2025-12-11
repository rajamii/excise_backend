import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'excise_backend.settings')
django.setup()

from models.transactional.supply_chain.ena_revalidation_details.models import EnaRevalidationDetail
from models.masters.supply_chain.status_master.models import StatusMaster, WorkflowRule

def debug_serializer_logic():
    ref_no = 'IBPS/01/EXCISE'
    print(f"DEBUGGING logic for Ref No: {ref_no}")
    
    try:
        obj = EnaRevalidationDetail.objects.filter(our_ref_no=ref_no).first()
        if not obj:
            print("Object not found!")
            return

        print(f"Object Found. ID: {obj.id}")
        print(f"Status in DB: '{obj.status}'") # Quotes to check whitespace
        
        # 1. Check Status Master lookup
        status_obj = StatusMaster.objects.filter(status_name=obj.status).first()
        if not status_obj:
            print(f"❌ StatusMaster lookup FAILED for name '{obj.status}'")
            # Try fuzzy search?
            print("All Statuses:")
            for s in StatusMaster.objects.all():
                print(f"  - '{s.status_name}' ({s.status_code})")
            return
            
        print(f"✓ StatusMaster found: {status_obj.status_name} ({status_obj.status_code})")
        
        # 2. Check Workflow Rule lookup
        role = 'permit-section'
        print(f"Testing with role: '{role}'")
        
        rules = WorkflowRule.objects.filter(
            current_status__status_code=status_obj.status_code,
            allowed_role=role
        )
        
        print(f"Rules Query count: {rules.count()}")
        for rule in rules:
            print(f"  Rule: {rule.action} -> {rule.next_status.status_code}")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == '__main__':
    debug_serializer_logic()
