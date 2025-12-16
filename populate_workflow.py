import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'excise_backend.settings')
django.setup()

from models.masters.supply_chain.status_master.models import StatusMaster, WorkflowRule

def populate_requisition_rules():
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

    print("\n" + "="*80)
    print("POPULATING REQUISITION WORKFLOW RULES")
    print("="*80 + "\n")
    
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
                print(f"[CREATED]: {current_status.status_name} + {action} ({role}) -> {next_status.status_name}")
            else:
                print(f"[UPDATED]: {current_status.status_name} + {action} ({role}) -> {next_status.status_name}")
                
        except StatusMaster.DoesNotExist as e:
            print(f"[ERROR]: {e}")
    
    requisition_count = WorkflowRule.objects.filter(current_status__status_code__startswith='RQ').count()
    print(f"\nTotal requisition rules: {requisition_count}")


def populate_revalidation_rules():
    """
    Populate workflow rules for ENA Revalidation Status Management.
    
    Workflow:
    1. Licensee submits -> RevalidationPending
    2. Permit Section approves -> ForwardedRevalidationToCommissioner
    3. Commissioner approves -> ApprovedRevalidation
    4. Commissioner rejects -> RejectedRevalidation
    5. Permit Section rejects -> RejectedRevalidation
    """
    print("Cleaning up erroneous rules for terminal states (RV_01, RV_02)...")
    terminate_statuses = ['RV_01', 'RV_02']
    WorkflowRule.objects.filter(current_status__status_code__in=terminate_statuses).delete()

    print("\n" + "="*80)
    print("POPULATING REVALIDATION WORKFLOW RULES")
    print("="*80 + "\n")
    
    # Format: (Current Status Code, Action, Next Status Code, Allowed Role)
    rules = [
        # Approval Flow
        ('RV_00', 'APPROVE', 'RV_17', 'permit-section'), # Pending -> ForwardedToCommissioner
        ('RV_17', 'APPROVE', 'RV_01', 'commissioner'),   # Forwarded -> Approved

        # Rejection Paths
        ('RV_00', 'REJECT', 'RV_02', 'permit-section'),  # Pending -> Rejected (assuming RV_02 is generic reject)
        ('RV_17', 'REJECT', 'RV_02', 'commissioner'),    # Forwarded -> Rejected

        # Invalid/Expired Handling (RV_18)
        ('RV_18', 'APPROVE', 'RV_17', 'permit-section'), # Invalid -> ForwardedToCommissioner
        ('RV_18', 'REJECT', 'RV_02', 'permit-section'),  # Invalid -> Rejected
    ]

    print("\n" + "="*80)
    print("POPULATING REVALIDATION WORKFLOW RULES")
    print("="*80 + "\n")
    
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
                print(f"[CREATED]: {current_status.status_name} + {action} ({role}) -> {next_status.status_name}")
            else:
                print(f"[UPDATED]: {current_status.status_name} + {action} ({role}) -> {next_status.status_name}")
                
        except StatusMaster.DoesNotExist as e:
            print(f"[ERROR]: {e}")
    
    revalidation_count = WorkflowRule.objects.filter(current_status__status_code__startswith='RV').count()
    print(f"\nTotal revalidation rules: {revalidation_count}")


def populate_cancellation_rules():
    """
    Populate workflow rules for ENA Cancellation Status Management.
    
    Workflow:
    1. Licensee submits -> CancellationPending (CN_00)
    2. Permit Section approves -> ForwardedCancellationToCommissioner (RQ_14)
    3. Commissioner approves -> ApprovedCancellationByCommissioner (RQ_19)
    4. Commissioner rejects -> RejectedCancellationByCommissioner (RQ_20)
    """
    print("\n" + "="*80)
    print("POPULATING CANCELLATION WORKFLOW RULES")
    print("="*80 + "\n")
    
    # Format: (Current Status Code, Action, Next Status Code, Allowed Role)
    rules = [
        # Approval Flow
        ('CN_00', 'APPROVE', 'RQ_14', 'permit-section'), # Pending -> Forwarded
        ('RQ_14', 'APPROVE', 'RQ_19', 'commissioner'),   # Forwarded -> Approved
        
        # Rejection Paths
        ('RQ_14', 'REJECT', 'RQ_20', 'commissioner'),    # Forwarded -> Rejected
    ]
    
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
                print(f"[CREATED]: {current_status.status_name} + {action} ({role}) -> {next_status.status_name}")
            else:
                print(f"[UPDATED]: {current_status.status_name} + {action} ({role}) -> {next_status.status_name}")
                
        except StatusMaster.DoesNotExist as e:
            print(f"[ERROR]: {e}")
            
    cancellation_count = WorkflowRule.objects.filter(current_status__status_code__in=['CN_00', 'RQ_14']).count()
    print(f"\nTotal cancellation rules: {cancellation_count}")

if __name__ == '__main__':
    populate_requisition_rules()
    populate_revalidation_rules()
    populate_cancellation_rules()
    
    print("\n" + "="*80)
    print("WORKFLOW RULES POPULATION COMPLETE")
    print("="*80)
    total_count = WorkflowRule.objects.count()
    print(f"\nTotal workflow rules in database: {total_count}\n")
