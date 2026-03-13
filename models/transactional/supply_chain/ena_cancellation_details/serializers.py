from rest_framework import serializers
from .models import EnaCancellationDetail
from auth.workflow.constants import WORKFLOW_IDS
import re

class EnaCancellationDetailSerializer(serializers.ModelSerializer):
    allowed_actions = serializers.SerializerMethodField()
    establishment_name = serializers.SerializerMethodField()
    payment_completed = serializers.SerializerMethodField()

    class Meta:
        model = EnaCancellationDetail
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

    def get_payment_completed(self, obj):
        try:
            from models.transactional.payment.models import WalletTransaction

            return WalletTransaction.objects.filter(
                source_module='ena_cancellation',
                reference_no=obj.our_ref_no,
                entry_type='DR',
                payment_status__iexact='success'
            ).exists()
        except Exception as e:
            print(f"Payment completion lookup failed for cancellation {obj.id}: {e}")
            return False

    def get_allowed_actions(self, obj):
        request = self.context.get('request')
        print(f"\n=== GET_ALLOWED_ACTIONS DEBUG (CANCELLATION) ===")
        print(f"Cancellation ID: {obj.id}, Status: {obj.status}")
        print(f"Current Stage ID: {obj.current_stage_id if hasattr(obj, 'current_stage_id') else 'N/A'}")
        print(f"Workflow ID: {obj.workflow_id if hasattr(obj, 'workflow_id') else 'N/A'}")
        
        if not request or not hasattr(request, 'user'):
            print("❌ No request or user")
            return []
        
        # Get user role name
        user_role_name = request.user.role.name if hasattr(request.user, 'role') and request.user.role else None
        print(f"User role name (raw): '{user_role_name}'")
        
        if not user_role_name:
            print("❌ No user role name found")
            return []
            
        user_role_name = user_role_name.strip()
        
        # Determine role and normalize it to match WorkflowRule expected values
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
            
        # Fallback for status_code if missing (legacy data)
        status_code = obj.status_code
        if not status_code:
            status_code = 'CN_00'
            
        # Query Workflow Transitions (New Logic)
        from auth.workflow.models import WorkflowTransition, WorkflowStage
        
        current_stage = obj.current_stage
        if not current_stage:
            # Fallback
            try:
                current_stage = WorkflowStage.objects.get(
                    workflow_id=WORKFLOW_IDS['ENA_CANCELLATION'],
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
        # Cancellation final stage: current_stage_id = 72, workflow_id = 5
        current_stage_id = obj.current_stage.id if obj.current_stage else None
        workflow_id = obj.workflow_id if hasattr(obj, 'workflow_id') else None
        
        print(f"Checking VIEW_PERMIT_SLIP conditions:")
        print(f"  - Role: {role} (need: commissioner or officer-in-charge)")
        print(f"  - Current Stage ID: {current_stage_id} (need: 72)")
        print(f"  - Workflow ID: {workflow_id} (need: 5)")
        
        if role in ['commissioner', 'officer-in-charge']:
            if current_stage_id == 72 and workflow_id == 5:
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
        existing_refs = EnaCancellationDetail.objects.values_list('our_ref_no', flat=True)
        pattern = r'CAN/(\d+)/EXCISE'
        numbers = []

        for ref in existing_refs:
            match = re.match(pattern, str(ref or ''))
            if match:
                numbers.append(int(match.group(1)))

        next_number = (max(numbers) + 1) if numbers else 1
        validated_data['our_ref_no'] = f"CAN/{next_number:02d}/EXCISE"
        
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
                        print(f"✅ Stored establishment_name in cancellation: {establishment_name}")
            except Exception as e:
                print(f"⚠️ Could not fetch establishment_name: {e}")
        
        return super().create(validated_data)

class CancellationCreateSerializer(serializers.Serializer):
    reference_no = serializers.CharField(max_length=100)
    permit_numbers = serializers.ListField(child=serializers.CharField(max_length=100))
    licensee_id = serializers.CharField(max_length=50, required=False, allow_blank=True)

