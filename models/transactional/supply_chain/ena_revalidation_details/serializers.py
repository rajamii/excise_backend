from rest_framework import serializers
from .models import EnaRevalidationDetail
from auth.workflow.constants import WORKFLOW_IDS
import re

class EnaRevalidationDetailSerializer(serializers.ModelSerializer):
    allowed_actions = serializers.SerializerMethodField()
    establishment_name = serializers.SerializerMethodField()

    class Meta:
        model = EnaRevalidationDetail
        fields = '__all__'
        extra_kwargs = {
            'our_ref_no': {'required': False},
        }

    def get_establishment_name(self, obj):
        """Return establishment_name from stored field or fetch from License if not stored"""
        # First, check if establishment_name is already stored in the record
        if obj.establishment_name:
            return obj.establishment_name
        
        # If not stored, fetch from License (for backward compatibility with old records)
        if not obj.licensee_id:
            return obj.distillery_name or ''
        
        from models.masters.license.models import License
        
        try:
            license_obj = License.objects.filter(
                license_id=obj.licensee_id,
                is_active=True
            ).select_related('source_content_type').first()
            
            if license_obj and license_obj.source_application:
                establishment_name = getattr(license_obj.source_application, 'establishment_name', None)
                if establishment_name:
                    return establishment_name
        except Exception as e:
            print(f"❌ Error fetching from License: {e}")
        
        return obj.distillery_name or ''

    def get_allowed_actions(self, obj):
        request = self.context.get('request')
        print(f"\n=== GET_ALLOWED_ACTIONS DEBUG (REVALIDATION) ===")
        print(f"Request: {request}")
        print(f"Revalidation ID: {obj.id}, Status: {obj.status}")
        print(f"Current Stage ID: {obj.current_stage_id if hasattr(obj, 'current_stage_id') else 'N/A'}")
        print(f"Workflow ID: {obj.workflow_id if hasattr(obj, 'workflow_id') else 'N/A'}")
        
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
        oic_roles = ['officer-in-charge', 'Officer-in-Charge', 'OIC', 'oic']
        licensee_roles = ['licensee', 'Licensee']
        
        if user_role_name in commissioner_roles:
            role = 'commissioner'
        elif user_role_name in permit_roles:
            role = 'permit-section'
        elif user_role_name in oic_roles:
            role = 'officer-in-charge'
        elif user_role_name in licensee_roles:
            role = 'licensee'
        
        print(f"Determined role: '{role}'")
        
        if not role:
            print(f"❌ Role not determined for '{user_role_name}'")
            return []

        # Query Workflow Transitions (New Logic)
        from auth.workflow.models import WorkflowTransition, WorkflowStage
        
        current_stage = obj.current_stage
        if not current_stage:
            # Fallback
            try:
                current_stage = WorkflowStage.objects.get(
                    workflow_id=WORKFLOW_IDS['ENA_REVALIDATION'],
                    name=obj.status
                )
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
        
        # Add VIEW_PERMIT_SLIP for commissioner/OIC at final stage
        # Revalidation final stage: current_stage_id = 47, workflow_id = 4
        current_stage_id = obj.current_stage.id if obj.current_stage else None
        workflow_id = obj.workflow_id if hasattr(obj, 'workflow_id') else None
        
        print(f"Checking VIEW_PERMIT_SLIP conditions:")
        print(f"  - Role: {role} (need: commissioner or officer-in-charge)")
        print(f"  - Current Stage ID: {current_stage_id} (need: 47)")
        print(f"  - Workflow ID: {workflow_id} (need: 4)")
        
        if role in ['commissioner', 'officer-in-charge']:
            if current_stage_id == 47 and workflow_id == 4:
                print("✅ Adding VIEW_PERMIT_SLIP action")
                actions.append('VIEW_PERMIT_SLIP')
            else:
                print("❌ Not at final stage for VIEW_PERMIT_SLIP")
        
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

    def create(self, validated_data):
        # IMPORTANT: Always generate a new REV reference number for revalidation
        # Remove any our_ref_no that might have been copied from requisition
        validated_data.pop('our_ref_no', None)
        
        existing_refs = EnaRevalidationDetail.objects.values_list('our_ref_no', flat=True)
        pattern = r'REV/(\d+)/EXCISE'
        numbers = []

        for ref in existing_refs:
            match = re.match(pattern, str(ref or ''))
            if match:
                numbers.append(int(match.group(1)))

        next_number = (max(numbers) + 1) if numbers else 1
        validated_data['our_ref_no'] = f"REV/{next_number:02d}/EXCISE"

        request = self.context.get('request')
        if request:
            requested_licensee_id = request.data.get('licensee_id') or request.data.get('licenseeId')
            if requested_licensee_id:
                validated_data['licensee_id'] = requested_licensee_id

        if not validated_data.get('licensee_id') and request and hasattr(request.user, 'supply_chain_profile'):
            validated_data['licensee_id'] = request.user.supply_chain_profile.licensee_id
        elif not validated_data.get('licensee_id') and request and hasattr(request.user, 'manufacturing_units'):
            unit = request.user.manufacturing_units.exclude(licensee_id__isnull=True).exclude(licensee_id='').first()
            if unit:
                validated_data['licensee_id'] = unit.licensee_id

        if not validated_data.get('licensee_id'):
            raise serializers.ValidationError({
                'licensee_id': 'Unable to determine licensee mapping. Please set your active supply-chain profile and try again.'
            })

        # Fetch and store establishment_name from License if licensee_id is provided
        if validated_data.get('licensee_id'):
            from models.masters.license.models import License
            try:
                license_obj = License.objects.filter(
                    license_id=validated_data['licensee_id'],
                    is_active=True
                ).select_related('source_content_type').first()
                
                if license_obj and license_obj.source_application:
                    establishment_name = getattr(license_obj.source_application, 'establishment_name', None)
                    if establishment_name:
                        validated_data['establishment_name'] = establishment_name
                        print(f"✅ Stored establishment_name in revalidation: {establishment_name}")
            except Exception as e:
                print(f"⚠️ Could not fetch establishment_name: {e}")

        return super().create(validated_data)
