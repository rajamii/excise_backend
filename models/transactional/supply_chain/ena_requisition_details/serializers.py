from rest_framework import serializers
from .models import EnaRequisitionDetail
import re

class EnaRequisitionDetailSerializer(serializers.ModelSerializer):
    allowed_actions = serializers.SerializerMethodField()

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

        # Query Workflow Rules
        from models.masters.supply_chain.status_master.models import WorkflowRule
        actions = WorkflowRule.objects.filter(
            current_status__status_code=obj.status_code,
            allowed_role=role
        ).values_list('action', flat=True)
        
        return list(actions)

    def create(self, validated_data):
        from models.masters.supply_chain.status_master.models import StatusMaster
        
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
        
        try:
            # Fetch the default status 'RQ_00' (Pending)
            status_obj = StatusMaster.objects.get(status_code='RQ_00')
            validated_data['status_code'] = status_obj.status_code
            validated_data['status'] = status_obj.status_name
        except StatusMaster.DoesNotExist:
            # Fallback or error handling if status master data is missing
            raise serializers.ValidationError("Default status 'RQ_00' not found in StatusMaster.")
            
        return super().create(validated_data)
