from rest_framework import serializers
from .models import EnaTransitPermitDetail
from auth.workflow.constants import WORKFLOW_IDS
from models.transactional.supply_chain.access_control import condition_role_matches

class EnaTransitPermitDetailSerializer(serializers.ModelSerializer):
    allowed_actions = serializers.SerializerMethodField()
    current_stage_name = serializers.CharField(source='current_stage.name', read_only=True)
    current_stage_description = serializers.CharField(source='current_stage.description', read_only=True)
    workflow_name = serializers.CharField(source='workflow.name', read_only=True)

    class Meta:
        model = EnaTransitPermitDetail
        fields = '__all__'

    def get_allowed_actions(self, obj):
        """
        Returns a list of allowed actions based on user role and current workflow stage.
        Queries WorkflowTransition table to dynamically determine allowed actions.
        """
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return []

        # Get user role
        user_role_name = request.user.role.name if hasattr(request.user, 'role') and request.user.role else None
        
        if not user_role_name:
            return []
        
        # Determine Role (Matching Frontend Logic)
        role = None
        normalized_role = ''.join(ch for ch in str(user_role_name or '').lower() if ch.isalnum())
        officer_aliases = {
            'level1', 'level2', 'level3', 'level4', 'level5', 'siteadmin',
            'officerincharge', 'offcierincharge', 'oic', 'officer'
        }

        if normalized_role in officer_aliases or hasattr(request.user, 'oic_assignment'):
            role = 'officer'
        elif normalized_role in {'licensee', 'licenseeuser', 'licenseuser'}:
            role = 'licensee'
        
        if not role:
            return []

        # Query Workflow Transitions
        from auth.workflow.models import WorkflowTransition, WorkflowStage
        
        current_stage = obj.current_stage
        if not current_stage:
            # Fallback: infer stage from status name
            try:
                current_stage = WorkflowStage.objects.get(
                    workflow_id=WORKFLOW_IDS['TRANSIT_PERMIT'],
                    name=obj.status
                )
            except WorkflowStage.DoesNotExist:
                return []

        transitions = WorkflowTransition.objects.filter(from_stage=current_stage)
        actions = []
        for t in transitions:
            cond = t.condition or {}
            if not condition_role_matches(cond, request.user):
                continue

            action = cond.get('action')
            if not action:
                stage_name = str(getattr(t.to_stage, 'name', '') or '').lower()
                if 'approved' in stage_name:
                    action = 'APPROVE'
                elif 'rejected' in stage_name or 'cancelled' in stage_name:
                    action = 'REJECT'
                elif 'payment' in stage_name and 'successful' in stage_name:
                    action = 'PAY'
                elif stage_name:
                    action = 'FORWARD'
            if action:
                actions.append(str(action).upper())

        return list(set(actions))  # Unique actions
    
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

class TransitPermitProductSerializer(serializers.Serializer):
    """
    Serializer to validate individual product items within the submission payload.
    """
    brand = serializers.CharField(max_length=255)
    size = serializers.CharField() # Input 'size'
    size = serializers.CharField() # Input 'size'
    cases = serializers.IntegerField()
    bottle_type = serializers.CharField(required=False, allow_blank=True) # New field
    # New fields
    brand_owner = serializers.CharField(required=False, allow_blank=True)
    liquor_type = serializers.CharField(required=False, allow_blank=True)
    ex_factory_price = serializers.DecimalField(max_digits=15, decimal_places=2, required=False) # Maps to exFactoryPrice
    excise_duty = serializers.DecimalField(max_digits=15, decimal_places=2, required=False) # Maps to exciseDuty
    education_cess = serializers.DecimalField(max_digits=15, decimal_places=2, required=False) # Maps to educationCess
    additional_excise = serializers.DecimalField(max_digits=15, decimal_places=2, required=False) # Maps to additionalExcise
    manufacturing_unit_name = serializers.CharField(required=False, allow_blank=True) # New field


class TransitPermitSubmissionSerializer(serializers.Serializer):
    """
    Serializer to validate the full submission payload.
    CamelCaseJSONParser will convert incoming camelCase keys to snake_case.
    """
    bill_no = serializers.CharField(required=False, allow_blank=True)
    sole_distributor = serializers.CharField() # maps from soleDistributor
    date = serializers.DateField()
    depot_address = serializers.CharField()
    vehicle_number = serializers.CharField()
    products = TransitPermitProductSerializer(many=True)

    def validate(self, attrs):
        return attrs
