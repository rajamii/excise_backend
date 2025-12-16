from rest_framework import serializers
from .models import EnaRevalidationDetail

class EnaRevalidationDetailSerializer(serializers.ModelSerializer):
    allowed_actions = serializers.SerializerMethodField()

    class Meta:
        model = EnaRevalidationDetail
        fields = '__all__'

    def get_allowed_actions(self, obj):
        request = self.context.get('request')
        print(f"\n=== GET_ALLOWED_ACTIONS DEBUG ===")
        print(f"Request: {request}")
        print(f"Revalidation ID: {obj.id}, Status: {obj.status}")
        
        if not request or not request.user.is_authenticated:
            print("❌ No request or user not authenticated")
            return []

        # Get user role name
        user_role_name = request.user.role.name if hasattr(request.user, 'role') and request.user.role else None
        print(f"User role name (raw): '{user_role_name}'")
        
        if not user_role_name:
            print("❌ No user role name found")
            return []
            
        user_role_name = user_role_name.strip() # Remove leading/trailing whitespace
        
        # Determine role (matching frontend logic)
        role = None
        commissioner_roles = ['level_1', 'level_2', 'level_3', 'level_4', 'level_5', 'Site-Admin', 'site_admin', 'commissioner', 'Commissioner']
        permit_roles = ['permit-section', 'Permit-Section', 'Permit Section', 'permit section']
        licensee_roles = ['licensee', 'Licensee']
        
        if user_role_name in commissioner_roles:
            role = 'commissioner'
        elif user_role_name in permit_roles:
            role = 'permit-section'
        elif user_role_name in licensee_roles:
            role = 'licensee'
        
        print(f"Determined role: '{role}'")
        
        if not role:
            print(f"❌ Role not determined for '{user_role_name}'")
            return []

        # Query Workflow Rules using status_name
        from models.masters.supply_chain.status_master.models import WorkflowRule, StatusMaster
        
        # Get status_obj using status_code if available (preferred)
        status_obj = None
        if hasattr(obj, 'status_code') and obj.status_code:
            status_obj = StatusMaster.objects.filter(status_code=obj.status_code).first()
            if status_obj:
                print(f"Status lookup by code ({obj.status_code}) successful: {status_obj.status_name}")
        
        # Fallback to name lookup
        if not status_obj:
            print(f"Status lookup by code failed or missing. Trying name: '{obj.status}'")
            status_obj = StatusMaster.objects.filter(status_name=obj.status).first()
            
        print(f"Status obj: {status_obj}")
        if status_obj:
            print(f"Status code: {status_obj.status_code}")
        
        if not status_obj:
            print(f"❌ No status found for status: {obj.status}")
            return []
        
        # Query workflow rules using status_code (like requisition does)
        rules = WorkflowRule.objects.filter(
            current_status__status_code=status_obj.status_code,
            allowed_role=role
        )
        print(f"Query: current_status__status_code={status_obj.status_code}, allowed_role={role}")
        print(f"Rules found: {rules.count()}")
        for rule in rules:
            print(f"  - {rule.action}: {rule.current_status.status_code} -> {rule.next_status.status_code}")
        
        actions = list(rules.values_list('action', flat=True))
        print(f"✓ Returning actions: {actions}\n")
        return actions
