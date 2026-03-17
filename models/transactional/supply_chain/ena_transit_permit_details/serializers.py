from rest_framework import serializers
from .models import EnaTransitPermitDetail
from auth.workflow.constants import WORKFLOW_IDS
from models.transactional.supply_chain.access_control import condition_role_matches

class EnaTransitPermitDetailSerializer(serializers.ModelSerializer):
    allowed_actions = serializers.SerializerMethodField()
    current_stage_name = serializers.CharField(source='current_stage.name', read_only=True)
    current_stage_description = serializers.CharField(source='current_stage.description', read_only=True)
    current_stage_is_initial = serializers.BooleanField(source='current_stage.is_initial', read_only=True)
    current_stage_is_final = serializers.BooleanField(source='current_stage.is_final', read_only=True)
    workflow_name = serializers.CharField(source='workflow.name', read_only=True)
    current_stage_entry_actions = serializers.SerializerMethodField()

    class Meta:
        model = EnaTransitPermitDetail
        fields = '__all__'

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if getattr(instance, 'current_stage', None):
            data['status'] = instance.current_stage.name
        return data

    def get_allowed_actions(self, obj):
        """
        Returns a list of allowed actions based on user role and current workflow stage.
        Queries WorkflowTransition table to dynamically determine allowed actions.
        """
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return []

        user_role = getattr(request.user, 'role', None)
        if not user_role:
            return []

        # Query Workflow Transitions
        from auth.workflow.models import WorkflowTransition, WorkflowStage

        current_stage = obj.current_stage
        if not current_stage:
            current_stage = WorkflowStage.objects.filter(
                workflow_id=WORKFLOW_IDS['TRANSIT_PERMIT'],
                is_initial=True
            ).first()
            if not current_stage:
                return []

        transitions = WorkflowTransition.objects.filter(from_stage=current_stage)
        actions = []
        for t in transitions:
            cond = t.condition or {}
            if not condition_role_matches(cond, request.user):
                continue

            action = cond.get('action')
            if action:
                actions.append(str(action).upper())

        return list(set(actions))  # Unique actions

    def get_current_stage_entry_actions(self, obj):
        """
        Returns actions that can move *into* the current stage.
        Useful for UI categorization without relying on stage-name strings.
        """
        if not obj.current_stage:
            return []

        from auth.workflow.models import WorkflowTransition

        actions = []
        incoming = WorkflowTransition.objects.filter(
            workflow_id=WORKFLOW_IDS['TRANSIT_PERMIT'],
            to_stage=obj.current_stage
        )
        for t in incoming:
            cond = t.condition or {}
            action = cond.get('action')
            if action:
                actions.append(str(action).upper())

        return sorted(list(set(actions)))
    
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
