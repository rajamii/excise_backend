from rest_framework import serializers
from .models import EnaTransitPermitDetail
from auth.workflow.constants import WORKFLOW_IDS
from models.transactional.supply_chain.access_control import condition_role_matches
from decimal import Decimal

class EnaTransitPermitDetailSerializer(serializers.ModelSerializer):
    size_ml = serializers.SerializerMethodField()
    liquor_type = serializers.SerializerMethodField()
    allowed_actions = serializers.SerializerMethodField()
    current_stage_name = serializers.CharField(source='current_stage.name', read_only=True)
    current_stage_description = serializers.CharField(source='current_stage.description', read_only=True)
    current_stage_is_initial = serializers.BooleanField(source='current_stage.is_initial', read_only=True)
    current_stage_is_final = serializers.BooleanField(source='current_stage.is_final', read_only=True)
    workflow_name = serializers.CharField(source='workflow.name', read_only=True)
    current_stage_entry_actions = serializers.SerializerMethodField()
    approved_by_display = serializers.SerializerMethodField()
    cancelled_by_display = serializers.SerializerMethodField()
    cancelled_reason_display = serializers.SerializerMethodField()

    def get_approved_by_display(self, obj):
        """Return the OIC name who approved this permit (from utilization record)."""
        # Stock utilization rows are created at PAY time (auto-deduction) and may set
        # `approved_by` to the payer/system. Only display "Approved By" to UI once the
        # Officer In-Charge has actually approved the permit.
        try:
            status_code = str(getattr(obj, 'status_code', '') or '').strip().upper()
            stage = getattr(obj, 'current_stage', None)
            stage_name = str(getattr(stage, 'name', '') or '').strip().lower()
            is_final = bool(getattr(stage, 'is_final', False))

            is_cancelled = 'cancel' in stage_name or 'reject' in stage_name or 'refund' in stage_name
            is_oic_approved = status_code == 'TRP_03' or (is_final and not is_cancelled and 'approv' in stage_name)

            if not is_oic_approved:
                return ''
        except Exception:
            # Fail safe: don't block API; fall through to existing logic.
            pass

        try:
            from models.transactional.supply_chain.brand_warehouse.models import BrandWarehouseUtilization
            util = BrandWarehouseUtilization.objects.filter(
                permit_no=obj.bill_no
            ).exclude(approved_by__isnull=True).exclude(approved_by='').first()
            if util:
                return util.approved_by or ''
        except Exception:
            pass
        return ''

    def get_cancelled_by_display(self, obj):
        """Return the OIC name who cancelled this permit (from cancellation record)."""
        try:
            from models.transactional.supply_chain.brand_warehouse.models import BrandWarehouseTpCancellation
            cancel = BrandWarehouseTpCancellation.objects.filter(
                reference_no=obj.bill_no
            ).exclude(cancelled_by__isnull=True).exclude(cancelled_by='').first()
            if cancel:
                return cancel.cancelled_by or ''
        except Exception:
            pass
        return ''

    def get_cancelled_reason_display(self, obj):
        """Return cancellation reason entered by admin/OIC for this permit."""
        try:
            from models.transactional.supply_chain.brand_warehouse.models import BrandWarehouseTpCancellation
            cancel = BrandWarehouseTpCancellation.objects.filter(
                reference_no=obj.bill_no
            ).exclude(reason__isnull=True).exclude(reason='').first()
            if cancel:
                return str(cancel.reason or '').strip()
        except Exception:
            pass
        return ''

    class Meta:
        model = EnaTransitPermitDetail
        fields = '__all__'

    def get_size_ml(self, obj) -> int:
        try:
            if getattr(obj, 'size_ml_id', None):
                return int(obj.size_ml)
        except Exception:
            pass
        return 0

    def get_liquor_type(self, obj) -> str:
        try:
            if getattr(obj, 'liquor_type_id', None):
                return str(obj.liquor_type or '').strip()
        except Exception:
            pass
        return ''

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if getattr(instance, 'current_stage', None):
            data['status'] = instance.current_stage.name

        self._enrich_missing_transit_fields(instance, data)
        return data

    def _get_cache(self):
        cache = getattr(self, '_transit_enrichment_cache', None)
        if cache is None:
            cache = {
                'warehouse': {},
                'liquor_data': {},
            }
            self._transit_enrichment_cache = cache
        return cache

    def _lookup_brand_warehouse(self, brand: str, size_ml: int, licensee_id: str):
        cache = self._get_cache()['warehouse']
        key = (str(brand or '').strip().lower(), int(size_ml or 0), str(licensee_id or '').strip().upper())
        if key in cache:
            return cache[key]

        try:
            from models.transactional.supply_chain.brand_warehouse.models import BrandWarehouse

            normalized_brand = str(brand or '').strip()
            size_ml_val = int(size_ml or 0)
            normalized_license = str(licensee_id or '').strip()
            if not normalized_brand or size_ml_val <= 0:
                cache[key] = None
                return None

            base = BrandWarehouse.objects.select_related(
                'brand', 'factory', 'liquor_type', 'capacity_size'
            ).filter(
                brand__brand_name__iexact=normalized_brand,
                capacity_size__size_ml=size_ml_val,
            )

            row = None
            if normalized_license:
                row = base.filter(license_id__iexact=normalized_license).first()
            if not row:
                row = base.first()

            cache[key] = row
            return row
        except Exception:
            cache[key] = None
            return None

    def _lookup_liquor_data(self, warehouse_row, brand: str, size_ml: int):
        cache = self._get_cache()['liquor_data']
        key = (str(brand or '').strip().lower(), int(size_ml or 0), int(getattr(warehouse_row, 'liquor_data_id', 0) or 0))
        if key in cache:
            return cache[key]

        try:
            from models.masters.supply_chain.liquor_data.models import LiquorData

            liquor_data_id = getattr(warehouse_row, 'liquor_data_id', None) if warehouse_row else None
            if liquor_data_id:
                row = LiquorData.objects.filter(id=liquor_data_id).first()
                cache[key] = row
                return row

            normalized_brand = str(brand or '').strip()
            size_ml_val = int(size_ml or 0)
            if not normalized_brand or size_ml_val <= 0:
                cache[key] = None
                return None

            row = (
                LiquorData.objects.filter(brand_name__iexact=normalized_brand, pack_size_ml=size_ml_val)
                .order_by('-updated_at', '-id')
                .first()
            )
            cache[key] = row
            return row
        except Exception:
            cache[key] = None
            return None

    def _parse_decimal(self, value):
        try:
            if value is None or value == '':
                return Decimal('0')
            return Decimal(str(value))
        except Exception:
            return Decimal('0')

    def _enrich_missing_transit_fields(self, instance: EnaTransitPermitDetail, data: dict) -> None:
        """
        Ensure Brand Owner / Manufacturing Unit / Amounts are available in API response.

        Older rows (or deployments where the UI didn't submit enriched fields) can have empty
        `brand_owner`, `manufacturing_unit_name`, and amount fields. Enrich using BrandWarehouse
        + LiquorData (brand + pack size).
        """
        try:
            size_ml_val = 0
            try:
                if getattr(instance, 'size_ml_id', None) and getattr(instance, 'size_ml', None) is not None:
                    size_ml_val = int(instance.size_ml)
            except Exception:
                size_ml_val = 0

            brand = str(getattr(instance, 'brand', '') or '').strip()
            licensee_id = str(getattr(instance, 'licensee_id', '') or '').strip()
            if not brand or size_ml_val <= 0:
                return

            warehouse_row = self._lookup_brand_warehouse(brand, size_ml_val, licensee_id)
            liquor_data_row = self._lookup_liquor_data(warehouse_row, brand, size_ml_val)

            # Manufacturing unit
            if not str(data.get('manufacturing_unit_name') or '').strip():
                manufacturing_unit = ''
                if warehouse_row:
                    manufacturing_unit = str(getattr(warehouse_row, 'distillery_name', '') or '').strip()
                if not manufacturing_unit and liquor_data_row:
                    manufacturing_unit = str(getattr(liquor_data_row, 'manufacturing_unit_name', '') or '').strip()
                if manufacturing_unit:
                    data['manufacturing_unit_name'] = manufacturing_unit

            # Brand owner
            if not str(data.get('brand_owner') or '').strip():
                brand_owner = ''
                if liquor_data_row:
                    brand_owner = str(getattr(liquor_data_row, 'brand_owner', '') or '').strip()
                if brand_owner:
                    data['brand_owner'] = brand_owner

            # Liquor type display (serializer field is string)
            if not str(data.get('liquor_type') or '').strip():
                liquor_type_name = ''
                try:
                    if warehouse_row and getattr(warehouse_row, 'liquor_type_id', None) and getattr(warehouse_row, 'liquor_type', None):
                        liquor_type_name = str(warehouse_row.liquor_type or '').strip()
                except Exception:
                    liquor_type_name = ''
                if not liquor_type_name and liquor_data_row:
                    liquor_type_name = str(getattr(liquor_data_row, 'liquor_type', '') or '').strip()
                if liquor_type_name:
                    data['liquor_type'] = liquor_type_name

            # Per-case rates: prefer stored values; otherwise derive from warehouse row.
            per_case_fields = [
                ('exfactory_price_rs_per_case', 'ex_factory_price_rs_per_case'),
                ('excise_duty_rs_per_case', 'excise_duty_rs_per_case'),
                ('education_cess_rs_per_case', 'education_cess_rs_per_case'),
                ('additional_excise_duty_rs_per_case', 'additional_excise_duty_rs_per_case'),
            ]
            for api_field, warehouse_attr in per_case_fields:
                current = self._parse_decimal(data.get(api_field))
                if current > 0:
                    continue
                if warehouse_row:
                    derived = self._parse_decimal(getattr(warehouse_row, warehouse_attr, 0) or 0)
                    if derived > 0:
                        data[api_field] = str(derived)

            cases = 0
            try:
                cases = int(getattr(instance, 'cases', 0) or 0)
            except Exception:
                cases = 0

            if cases <= 0:
                return

            # Totals: compute if missing/zero.
            excise_per_case = self._parse_decimal(data.get('excise_duty_rs_per_case'))
            education_per_case = self._parse_decimal(data.get('education_cess_rs_per_case'))
            additional_per_case = self._parse_decimal(data.get('additional_excise_duty_rs_per_case'))

            if self._parse_decimal(data.get('total_excise_duty')) <= 0 and excise_per_case > 0:
                data['total_excise_duty'] = str(excise_per_case * cases)
            if self._parse_decimal(data.get('total_education_cess')) <= 0 and education_per_case > 0:
                data['total_education_cess'] = str(education_per_case * cases)
            if self._parse_decimal(data.get('total_additional_excise')) <= 0 and additional_per_case > 0:
                data['total_additional_excise'] = str(additional_per_case * cases)

            if self._parse_decimal(data.get('total_amount')) <= 0:
                total_per_case = excise_per_case + education_per_case + additional_per_case
                if total_per_case > 0:
                    data['total_amount'] = str(total_per_case * cases)
        except Exception:
            # Never break API responses due to enrichment.
            return

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


class PublicTransitPermitDetailSerializer(serializers.ModelSerializer):
    """
    Public-facing (no-auth) transit permit serializer.
    Intentionally exposes a limited set of fields for external consumption.
    """

    size_ml = serializers.SerializerMethodField()
    liquor_type = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()
    status_code = serializers.CharField(read_only=True)
    current_stage_name = serializers.SerializerMethodField()
    current_stage_description = serializers.SerializerMethodField()

    class Meta:
        model = EnaTransitPermitDetail
        fields = (
            'bill_no',
            'sole_distributor_name',
            'date',
            'depot_address',
            'brand',
            'size_ml',
            'cases',
            'vehicle_number',
            'licensee_id',
            'status',
            'status_code',
            'current_stage_name',
            'current_stage_description',
            'bottle_type',
            'bottles_per_case',
            'brand_owner',
            'liquor_type',
            'manufacturing_unit_name',
            'total_amount',
            'driver_name',
            'driver_license_no',
            'transporter_name',
            'created_at',
            'updated_at',
        )

    def get_size_ml(self, obj) -> int:
        try:
            if getattr(obj, 'size_ml_id', None):
                return int(obj.size_ml)
        except Exception:
            pass
        return 0

    def get_liquor_type(self, obj) -> str:
        try:
            if getattr(obj, 'liquor_type_id', None):
                return str(obj.liquor_type or '').strip()
        except Exception:
            pass
        return ''

    def get_current_stage_name(self, obj) -> str:
        try:
            stage = getattr(obj, 'current_stage', None)
            return str(getattr(stage, 'name', '') or '').strip()
        except Exception:
            return ''

    def get_current_stage_description(self, obj) -> str:
        try:
            stage = getattr(obj, 'current_stage', None)
            return str(getattr(stage, 'description', '') or '').strip()
        except Exception:
            return ''

    def get_status(self, obj) -> str:
        """
        Public API should present a user-friendly status label.
        Prefer workflow stage description; fall back to stage name / stored status.
        """
        desc = self.get_current_stage_description(obj)
        if desc:
            return desc
        name = self.get_current_stage_name(obj)
        if name:
            return name
        return str(getattr(obj, 'status', '') or '').strip()
