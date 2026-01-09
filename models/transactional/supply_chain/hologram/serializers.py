from rest_framework import serializers
from .models import HologramProcurement, HologramRequest
from auth.workflow.models import Transaction, Objection
from models.masters.supply_chain.profile.models import SupplyChainUserProfile

class HologramProcurementSerializer(serializers.ModelSerializer):
    licensee_name = serializers.CharField(source='licensee.manufacturing_unit_name', read_only=True)
    status = serializers.CharField(source='current_stage.name', read_only=True)
    stage_id = serializers.IntegerField(source='current_stage.id', read_only=True)
    allowed_actions = serializers.SerializerMethodField()
    workflow_name = serializers.CharField(source='workflow.name', read_only=True)
    carton_details = serializers.JSONField(required=False)
    total_available_holograms = serializers.SerializerMethodField()

    class Meta:
        model = HologramProcurement
        fields = '__all__'
        read_only_fields = ('ref_no', 'date', 'workflow', 'current_stage', 'payment_status', 'manufacturing_unit', 'licensee')

    def to_representation(self, instance):
        data = super().to_representation(instance)
        # Force carton_details to be present
        if 'carton_details' not in data:
            data['carton_details'] = instance.carton_details or []
        print(f"DEBUG: Serialized {instance.ref_no}. keys: {list(data.keys())} carton_details len: {len(data.get('carton_details', []))}")
        return data

    def get_total_available_holograms(self, obj):
        total = 0
        details = obj.carton_details or []
        for c in details:
            # Check for explicitly updated available_qty
            available = c.get('available_qty')
            
            if available is not None:
                total += int(available)
            else:
                # Fallback: If not yet tracked, use total count (minus used if present, just in case)
                total_cnt = int(c.get('numberOfHolograms') or c.get('number_of_holograms') or c.get('total_count') or 0)
                used = int(c.get('used_qty', 0))
                damaged = int(c.get('damage_qty', 0))
                total += max(0, total_cnt - used - damaged)
        return total

    def get_allowed_actions(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return []
        
        user_role_name = request.user.role.name if hasattr(request.user, 'role') and request.user.role else None
        if not user_role_name:
            return []

        # Map backend roles to workflow roles
        role = None
        commissioner_roles = ['level_1', 'level_2', 'level_3', 'level_4', 'level_5', 'Site-Admin', 'site_admin', 'commissioner', 'Commissioner']
        
        if user_role_name in commissioner_roles:
            role = 'commissioner'
        elif user_role_name in ['it_cell', 'IT Cell', 'IT-Cell']: # Adjust based on actual role name
            role = 'it_cell'
        elif user_role_name in ['officer_in_charge', 'Officer In-Charge', 'OIC']:
            role = 'officer_in_charge'
        elif user_role_name in ['licensee', 'Licensee']:
            role = 'licensee'
            
        if not role:
            return []

        # Find allowed transitions from current stage for this role
        from auth.workflow.models import WorkflowTransition
        if not obj.current_stage:
            return []
            
        transitions = WorkflowTransition.objects.filter(from_stage=obj.current_stage)
        actions = []
        for t in transitions:
            cond = t.condition or {}
            if cond.get('role') == role:
                action = cond.get('action')
                if action:
                    actions.append(action)
        return list(set(actions))

class HologramRequestSerializer(serializers.ModelSerializer):
    licensee_name = serializers.CharField(source='licensee.manufacturing_unit_name', read_only=True)
    status = serializers.CharField(source='current_stage.name', read_only=True)
    stage_id = serializers.IntegerField(source='current_stage.id', read_only=True)
    allowed_actions = serializers.SerializerMethodField()
    workflow_name = serializers.CharField(source='workflow.name', read_only=True)
    available_cartons = serializers.SerializerMethodField()

    class Meta:
        model = HologramRequest
        fields = ['id', 'ref_no', 'submission_date', 'usage_date', 'quantity', 'hologram_type', 'issued_assets', 'rolls_assigned', 'licensee', 'licensee_name', 'workflow', 'workflow_name', 'current_stage', 'status', 'stage_id', 'allowed_actions', 'available_cartons']
        read_only_fields = ('ref_no', 'submission_date', 'workflow', 'current_stage', 'licensee')
    
    def to_representation(self, instance):
        """Add logging to debug issued_assets"""
        ret = super().to_representation(instance)
        print(f"DEBUG SERIALIZER: Request {ret.get('ref_no')} - issued_assets: {ret.get('issued_assets')}")
        return ret

    def get_available_cartons(self, obj):
        """
        Auto-pull carton details from hologram_procurement for this licensee.
        Returns all cartons from procurements that have been assigned (have carton_details).
        """
        try:
            procurements = HologramProcurement.objects.filter(
                licensee=obj.licensee
            ).exclude(carton_details__isnull=True).exclude(carton_details=[])
            
            cartons = []
            for proc in procurements:
                if proc.carton_details:
                    for carton in proc.carton_details:
                        carton_copy = dict(carton)  # Copy to avoid modifying original
                        carton_copy['procurement_ref'] = proc.ref_no
                        carton_copy['procurement_id'] = proc.id
                        cartons.append(carton_copy)
            return cartons
        except Exception as e:
            print(f"Error fetching available cartons: {e}")
            return []

    def get_allowed_actions(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return []
        
        user_role_name = request.user.role.name if hasattr(request.user, 'role') and request.user.role else None
        if not user_role_name:
            return []

        role = None
        # Permit Section Logic
        if user_role_name in ['permit-section', 'Permit-Section', 'Permit Section']:
            role = 'permit-section'
        elif user_role_name in ['officer_in_charge', 'Officer In-Charge', 'OIC', 'officer-incharge', 'Officer-Incharge', 'Officer In Charge', 'Officer in Charge', 'Officer in charge']:
            role = 'officer_in_charge'
        elif user_role_name in ['licensee', 'Licensee']:
            role = 'licensee'

        if not role:
            return []

        from auth.workflow.models import WorkflowTransition
        if not obj.current_stage:
            return []
            
        transitions = WorkflowTransition.objects.filter(from_stage=obj.current_stage)
        actions = []
        for t in transitions:
            cond = t.condition or {}
            if cond.get('role') == role:
                action = cond.get('action')
                if action:
                    actions.append(action)
        return list(set(actions))

class TransactionSerializer(serializers.ModelSerializer):
    performed_by_name = serializers.CharField(source='performed_by.username', read_only=True)
    stage_name = serializers.CharField(source='stage.name', read_only=True)
    
    class Meta:
        model = Transaction
        fields = '__all__'

from .models import DailyHologramRegister

class DailyHologramRegisterSerializer(serializers.ModelSerializer):
    licensee_name = serializers.CharField(source='licensee.manufacturing_unit_name', read_only=True)
    
    class Meta:
        model = DailyHologramRegister
        fields = '__all__'
        read_only_fields = ('submission_date', 'licensee')

from .models import HologramRollsDetails

class HologramRollsDetailsSerializer(serializers.ModelSerializer):
    procurement_ref = serializers.CharField(source='procurement.ref_no', read_only=True)
    
    class Meta:
        model = HologramRollsDetails
        fields = '__all__'
