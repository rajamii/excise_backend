from rest_framework import serializers
from .models import EnaRequisitionDetail
import re

class EnaRequisitionDetailSerializer(serializers.ModelSerializer):
    allowed_actions = serializers.SerializerMethodField()
    can_initiate_cancellation = serializers.SerializerMethodField()
    
    current_stage_name = serializers.CharField(source='current_stage.name', read_only=True)
    workflow_name = serializers.CharField(source='workflow.name', read_only=True)

    class Meta:
        model = EnaRequisitionDetail
        fields = '__all__'
        extra_kwargs = {
            'status': {'required': False},
            'status_code': {'required': False},
            'our_ref_no': {'required': False},  # Auto-generated
        }

    def get_allowed_actions(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return []

        # CustomUser uses 'role' field, not 'groups'
        # Check if user has a role and get its name
        user_role_name = request.user.role.name if hasattr(request.user, 'role') and request.user.role else None
        
        if not user_role_name:
            return []
        
        # Determine Role (Matching Frontend Logic)
        role = None
        commissioner_roles = ['level_1', 'level_2', 'level_3', 'level_4', 'level_5', 'Site-Admin', 'site_admin', 'commissioner', 'Commissioner']
        
        if user_role_name in commissioner_roles:
            role = 'commissioner'
        elif user_role_name in ['permit-section', 'Permit-Section', 'Permit Section']:
            role = 'permit-section'
        elif user_role_name in ['licensee', 'Licensee']:
            role = 'licensee'
        
        if not role:
            return []

        # Query Workflow Transitions (New Logic)
        from auth.workflow.models import WorkflowTransition, WorkflowStage
        
        current_stage = obj.current_stage
        if not current_stage:
            # Fallback: infer stage from status name
            try:
                # Assuming 'Supply Chain' workflow
                current_stage = WorkflowStage.objects.get(workflow__name='Supply Chain', name=obj.status)
            except WorkflowStage.DoesNotExist:
                return []

        transitions = WorkflowTransition.objects.filter(from_stage=current_stage)
        actions = []
        for t in transitions:
            cond = t.condition or {}
            # Check if role matches
            if cond.get('role') == role:
                action = cond.get('action')
                if action:
                    actions.append(action)
        
        return list(set(actions)) # Unique actions

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
