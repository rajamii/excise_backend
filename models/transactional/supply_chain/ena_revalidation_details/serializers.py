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

        if not role:
            return []

        # Query Workflow Transitions (New Logic)
        from auth.workflow.models import WorkflowTransition, WorkflowStage
        
        current_stage = obj.current_stage
        if not current_stage:
            # Fallback
            try:
                current_stage = WorkflowStage.objects.get(workflow__name='ENA Revalidation', name=obj.status)
            except WorkflowStage.DoesNotExist:
                return []

        transitions = WorkflowTransition.objects.filter(from_stage=current_stage)
        actions = []
        for t in transitions:
            cond = t.condition or {}
            if cond.get('role') == role:
                action = cond.get('action')
                if action:
                    actions.append(action)
        
        return list(set(actions))

    # New Field: Returns Full UI Config for Actions
    allowed_action_configs = serializers.SerializerMethodField()

    def get_allowed_action_configs(self, obj):
        actions = self.get_allowed_actions(obj)
        if not actions:
            return []
        
        from auth.workflow.services import WorkflowService
        configs = []
        for action_name in actions:
            config = WorkflowService.get_action_config(action_name)
            configs.append(config)
        return configs
