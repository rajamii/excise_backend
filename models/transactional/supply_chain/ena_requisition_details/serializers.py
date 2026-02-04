from rest_framework import serializers
from .models import EnaRequisitionDetail
import re

class EnaRequisitionDetailSerializer(serializers.ModelSerializer):
    allowed_actions = serializers.SerializerMethodField()
    can_initiate_cancellation = serializers.SerializerMethodField()
    
    current_stage_name = serializers.CharField(source='current_stage.name', read_only=True)
    workflow_name = serializers.CharField(source='workflow.name', read_only=True)
    
    # Explicitly include our_ref_no to ensure it's serialized
    our_ref_no = serializers.CharField(read_only=True)

    class Meta:
        model = EnaRequisitionDetail
        fields = '__all__'
        extra_kwargs = {
            'status': {'required': False},
            'status_code': {'required': False},
            'our_ref_no': {'required': False},  # Auto-generated
        }
        
    def to_representation(self, instance):
        """Override to ensure all fields are always included"""
        data = super().to_representation(instance)
        
        # Explicitly ensure critical fields are included with proper values
        data['our_ref_no'] = instance.our_ref_no or ''
        data['lifted_from'] = instance.lifted_from or ''
        data['via_route'] = instance.via_route or ''
        data['check_post_name'] = instance.check_post_name or ''
        data['branch_purpose'] = instance.branch_purpose or ''
        data['lifted_from_distillery_name'] = instance.lifted_from_distillery_name or ''
        data['purpose_name'] = instance.purpose_name or ''
        data['totalbl'] = str(instance.totalbl) if instance.totalbl else '0'
        data['grain_ena_number'] = str(instance.grain_ena_number) if instance.grain_ena_number else '0'
        data['requisiton_number_of_permits'] = instance.requisiton_number_of_permits or 1
        data['bulk_spirit_type'] = instance.bulk_spirit_type or ''
        data['strength'] = instance.strength or ''
        data['status'] = instance.status or 'PENDING'
        
        print(f"DEBUG: Serializing requisition {instance.id}")
        print(f"  - our_ref_no: '{instance.our_ref_no}' -> '{data['our_ref_no']}'")
        print(f"  - lifted_from: '{instance.lifted_from}' -> '{data['lifted_from']}'")
        print(f"  - via_route: '{instance.via_route}' -> '{data['via_route']}'")
        print(f"  - check_post_name: '{instance.check_post_name}' -> '{data['check_post_name']}'")
        print(f"  - branch_purpose: '{instance.branch_purpose}' -> '{data['branch_purpose']}'")
        print(f"  - lifted_from_distillery_name: '{instance.lifted_from_distillery_name}' -> '{data['lifted_from_distillery_name']}'")
        print(f"  - purpose_name: '{instance.purpose_name}' -> '{data['purpose_name']}'")
        print(f"  - totalbl: {instance.totalbl} -> '{data['totalbl']}'")
        print(f"  - status: '{instance.status}' -> '{data['status']}'")
        
        return data

    def get_allowed_actions(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return []

        # CustomUser uses 'role' field, not 'groups'
        # Check if user has a role and get its name
        user_role_name = request.user.role.name if hasattr(request.user, 'role') and request.user.role else None
        
        if not user_role_name:
            return []
        
        # Normalize role name
        user_role_name = str(user_role_name).strip()
        cleaned_role_name = user_role_name.lower()
        
        # Determine Role (Matching Frontend Logic)
        role = None
        
        # Commissioner roles (add more aliases if needed)
        if cleaned_role_name in ['commissioner', 'level_1', 'level_2', 'level_3', 'level_4', 'level_5', 'site_admin', 'site-admin']:
            role = 'commissioner'
        # Permit Section roles
        elif cleaned_role_name in ['permit-section', 'permit section', 'permit_section']:
            role = 'permit-section'
        # Licensee roles
        elif cleaned_role_name in ['licensee', 'license user', 'license_user']:
            role = 'licensee'
        
        if not role:
            # Fallback for simple exact matches if not caught above
            role = cleaned_role_name
        
        # Query Workflow Transitions
        from auth.workflow.models import WorkflowTransition, WorkflowStage
        
        current_stage = obj.current_stage
        if not current_stage:
            try:
                # Assuming 'Supply Chain' workflow
                current_stage = WorkflowStage.objects.get(workflow__name='Supply Chain', name=obj.status)
            except WorkflowStage.DoesNotExist:
                return []

        transitions = WorkflowTransition.objects.filter(from_stage=current_stage)
        actions = []
        for t in transitions:
            cond = t.condition or {}
            # Check if role matches (condition role should be compared case-insensitively or normalized)
            cond_role = str(cond.get('role', '')).lower()
            
            if cond_role == role.lower():
                action = cond.get('action')
                if action:
                    # Frontend expects UPPERCASE actions
                    actions.append(str(action).upper())
        
        return list(set(actions)) # Unique actions

    # New Field: Returns Full UI Config for Actions
    allowed_action_configs = serializers.SerializerMethodField()

    def get_allowed_action_configs(self, obj):
        # 1. Get standard workflow actions
        actions = self.get_allowed_actions(obj)
        
        # 2. Check for "Request Cancellation" specific logic
        if self.get_can_initiate_cancellation(obj):
            if 'REQUEST_CANCELLATION' not in actions:
                actions.append('REQUEST_CANCELLATION')

        if not actions:
            return []
        
        from auth.workflow.services import WorkflowService
        configs = []
        for action_name in actions:
            config = WorkflowService.get_action_config(action_name)
            configs.append(config)
        
        return configs

    def get_can_initiate_cancellation(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return False
            
        # Only Licensee can initiate cancellation
        user_role_name = request.user.role.name if hasattr(request.user, 'role') and request.user.role else None
        if user_role_name not in ['licensee', 'Licensee']:
            return False

        # Status must be 'RQ_09' (Approved)
        # We explicitly check for the code here in the backend business logic
        return obj.status_code == 'RQ_09'

    def create(self, validated_data):
        # from models.masters.supply_chain.status_master.models import StatusMaster # Removed
        
        # Auto-generate reference number
        existing_refs = EnaRequisitionDetail.objects.values_list('our_ref_no', flat=True)
        
        # Extract numeric parts from reference numbers
        numbers = []
        pattern = r'IBPS/(\d+)/EXCISE'
        
        for ref in existing_refs:
            match = re.match(pattern, ref)
            if match:
                numbers.append(int(match.group(1)))
        
        # Determine next number
        if numbers:
            next_number = max(numbers) + 1
        else:
            next_number = 1
        
        # Format the reference number
        validated_data['our_ref_no'] = f"IBPS/{next_number:02d}/EXCISE"
        
        # Auto-populate Licensee ID from Profile
        request = self.context.get('request')
        if request and request.user and hasattr(request.user, 'supply_chain_profile'):
            validated_data['licensee_id'] = request.user.supply_chain_profile.licensee_id
        
        # Initialize Workflow and Status
        from auth.workflow.models import Workflow, WorkflowStage
        try:
            workflow = Workflow.objects.get(name="Supply Chain")
            initial_stage = WorkflowStage.objects.get(workflow=workflow, is_initial=True)
            
            validated_data['workflow'] = workflow
            validated_data['current_stage'] = initial_stage
            
            # Use stage name for status, and default 'RQ_00' for status_code
            validated_data['status'] = initial_stage.name
            validated_data['status_code'] = 'RQ_00'
            
        except Exception as e:
            # Fallback for robustness
            print(f"Workflow initialization failed: {e}")
            validated_data['status'] = 'Pending'
            validated_data['status_code'] = 'RQ_00'
            
        return super().create(validated_data)
