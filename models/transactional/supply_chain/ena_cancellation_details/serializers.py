from rest_framework import serializers
from .models import EnaCancellationDetail
from auth.workflow.constants import WORKFLOW_IDS
import logging
import re

logger = logging.getLogger(__name__)

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
            logger.exception(
                "Error fetching establishment_name from License (licensee_id=%s)",
                getattr(obj, "licensee_id", None),
            )
        
        return obj.distillery_name or ''

    def get_payment_completed(self, obj):
        try:
            from models.transactional.wallet.models import WalletTransaction

            return WalletTransaction.objects.filter(
                source_module='ena_cancellation',
                reference_no=obj.our_ref_no,
                entry_type='DR',
                payment_status__iexact='success'
            ).exists()
        except Exception as e:
            logger.exception("Payment completion lookup failed for cancellation=%s", getattr(obj, "id", None))
            return False

    def get_allowed_actions(self, obj):
        request = self.context.get('request')
        logger.debug(
            "ENA cancellation allowed_actions: id=%s status=%s current_stage_id=%s workflow_id=%s",
            getattr(obj, "id", None),
            getattr(obj, "status", None),
            getattr(obj, "current_stage_id", None) if hasattr(obj, "current_stage_id") else None,
            getattr(obj, "workflow_id", None) if hasattr(obj, "workflow_id") else None,
        )
        
        if not request or not hasattr(request, 'user'):
            return []
        
        # Get user role name
        user_role_name = request.user.role.name if hasattr(request.user, 'role') and request.user.role else None
        logger.debug("ENA cancellation allowed_actions: user_role_name(raw)=%r", user_role_name)
        
        if not user_role_name:
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
        
        logger.debug("ENA cancellation allowed_actions: determined_role=%r", role)
        
        if not role:
            logger.debug("ENA cancellation allowed_actions: role not determined for user_role_name=%r", user_role_name)
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

        # Add VIEW_PERMIT_SLIP using stage semantics instead of hardcoded stage id.
        current_stage_obj = obj.current_stage
        workflow_id = obj.workflow_id if hasattr(obj, 'workflow_id') else None
        stage_name_lower = str(getattr(current_stage_obj, 'name', '') or '').lower()
        is_stage_final = bool(getattr(current_stage_obj, 'is_final', False))

        is_rejected = 'reject' in stage_name_lower
        is_commissioner_approved = 'commissioner' in stage_name_lower and 'approv' in stage_name_lower
        # Permit slip must be visible only after commissioner approval stage.
        is_viewable_stage = is_commissioner_approved or (is_stage_final and not is_rejected and 'approv' in stage_name_lower)

        logger.debug(
            "ENA cancellation VIEW_PERMIT_SLIP check: role=%s workflow_id=%s stage=%s final=%s viewable=%s",
            role,
            workflow_id,
            getattr(current_stage_obj, 'name', 'N/A'),
            is_stage_final,
            is_viewable_stage,
        )

        if (
            role in ['commissioner', 'officer-in-charge']
            and workflow_id == WORKFLOW_IDS['ENA_CANCELLATION']
            and is_viewable_stage
        ):
            logger.debug("ENA cancellation allowed_actions: adding VIEW_PERMIT_SLIP")
            actions.append('VIEW_PERMIT_SLIP')

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
                        logger.debug(
                            "Stored establishment_name in cancellation create (licensee_id=%s)",
                            validated_data.get('licensee_id'),
                        )
            except Exception as e:
                logger.exception(
                    "Could not fetch establishment_name during cancellation create (licensee_id=%s)",
                    validated_data.get('licensee_id'),
                )
        
        return super().create(validated_data)

class CancellationCreateSerializer(serializers.Serializer):
    reference_no = serializers.CharField(max_length=100)
    permit_numbers = serializers.ListField(child=serializers.CharField(max_length=100))
    licensee_id = serializers.CharField(max_length=50, required=False, allow_blank=True)


