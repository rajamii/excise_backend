import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'excise_backend.settings')
django.setup()

from models.masters.supply_chain.status_master.models import StatusMaster, WorkflowRule

def populate_rules():
    """
    Populate workflow rules for ENA Requisition Status Management.
    
    Workflow:
    1. Licensee submits -> Pending
    2. Permit Section approves -> ForwardedToCommissioner
    3. Commissioner approves -> ApprovedByCommissioner
    4. Licensee submits payslip -> ForwardedPaySLipToPermitSection
    5. Permit Section forwards -> ForwardedPaySLipToCommissioner
    6. Commissioner final approval -> Approved
    """
    # Format: (Current Status Code, Action, Next Status Code, Allowed Role)
    rules = [
        # Approval Flow
        ('RQ_00', 'APPROVE', 'RQ_03', 'permit-section'),
        ('RQ_03', 'APPROVE', 'RQ_04', 'commissioner'),
        ('RQ_04', 'APPROVE', 'RQ_07', 'licensee'),
        ('RQ_07', 'APPROVE', 'RQ_08', 'permit-section'),
        ('RQ_08', 'APPROVE', 'RQ_09', 'commissioner'),

        # Rejection Paths
        ('RQ_00', 'REJECT', 'RQ_10', 'permit-section'),
        ('RQ_03', 'REJECT', 'RQ_10', 'commissioner'),
        ('RQ_07', 'REJECT', 'RQ_10', 'permit-section'),
        ('RQ_08', 'REJECT', 'RQ_05', 'commissioner'),
    ]

    print("Populating Workflow Rules...")
    
    for current_code, action, next_code, role in rules:
        try:
            current_status = StatusMaster.objects.get(status_code=current_code)
            next_status = StatusMaster.objects.get(status_code=next_code)
            
            rule, created = WorkflowRule.objects.update_or_create(
                current_status=current_status,
                action=action,
                allowed_role=role,
                defaults={'next_status': next_status}
            )
            
            if created:
                print(f"✓ Created: {current_status.status_name} + {action} ({role}) -> {next_status.status_name}")
            else:
                print(f"↻ Updated: {current_status.status_name} + {action} ({role}) -> {next_status.status_name}")
                
        except StatusMaster.DoesNotExist as e:
            print(f"✗ Error: {e}")
    
    print(f"\nTotal rules: {WorkflowRule.objects.count()}")


if __name__ == '__main__':
    populate_rules()
