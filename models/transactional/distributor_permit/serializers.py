from decimal import Decimal

from rest_framework import serializers

from models.masters.supply_chain.liquor_data.models import LiquorData, MasterBrandList
from models.masters.supply_chain.transit_permit.models import BrandMlInCases

from .models import (
    DistributorPermitApplication,
    DistributorPermitDocument,
    DistributorPermitLineItem,
    IMFLRevalidation,
    IMFLCancellation,
    IMFLRevalidationActivationSchedule,
)


class DistributorPermitLineItemSerializer(serializers.ModelSerializer):
    brand_id = serializers.PrimaryKeyRelatedField(
        source='brand',
        queryset=MasterBrandList.objects.all(),
        write_only=True,
    )
    brand_master_id = serializers.IntegerField(source='brand_id', read_only=True)

    class Meta:
        model = DistributorPermitLineItem
        fields = [
            'id',
            'brand_id',
            'brand_master_id',
            'brand_name',
            'size_ml',
            'pieces_per_case',
            'cases',
            'edp_per_case',
            'import_pass_fee_per_case',
            'mrp_per_bottle',
            'additional_ed_per_case',
            'education_cess_per_case',
            'total_import',
            'total_education_cess',
            'total_additional_ed',
            'bulk_litres',
        ]
        read_only_fields = [
            'id',
            'brand_name',
            'pieces_per_case',
            'edp_per_case',
            'import_pass_fee_per_case',
            'mrp_per_bottle',
            'additional_ed_per_case',
            'education_cess_per_case',
            'total_import',
            'total_education_cess',
            'total_additional_ed',
            'bulk_litres',
        ]

    def to_internal_value(self, data):
        data = data.copy() if hasattr(data, 'copy') else dict(data)
        mappings = {
            'brandId': 'brand_id',
            'sizeMl': 'size_ml',
        }
        for camel, snake in mappings.items():
            if camel in data and snake not in data:
                data[snake] = data[camel]
        return super().to_internal_value(data)

    def validate_cases(self, value):
        if value <= 0:
            raise serializers.ValidationError('Cases must be greater than zero.')
        return value

    def validate_size_ml(self, value):
        if value <= 0:
            raise serializers.ValidationError('Size must be greater than zero.')
        return value


class DistributorPermitDocumentSerializer(serializers.ModelSerializer):
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = DistributorPermitDocument
        fields = ['id', 'document_type', 'file', 'file_url', 'uploaded_at']
        read_only_fields = ['id', 'file_url', 'uploaded_at']

    def get_file_url(self, obj):
        request = self.context.get('request')
        if not obj.file:
            return ''
        if request:
            return request.build_absolute_uri(obj.file.url)
        return obj.file.url


class DistributorPermitApplicationSerializer(serializers.ModelSerializer):
    line_items = DistributorPermitLineItemSerializer(many=True)
    documents = DistributorPermitDocumentSerializer(many=True, read_only=True)
    applicant_name = serializers.SerializerMethodField()
    brand_count = serializers.SerializerMethodField()
    total_cases = serializers.SerializerMethodField()
    total_import_value = serializers.SerializerMethodField()
    total_education_cess = serializers.SerializerMethodField()
    total_additional_ed = serializers.SerializerMethodField()
    total_bulk_litres = serializers.SerializerMethodField()
    allowed_actions = serializers.SerializerMethodField()
    allowedActions = serializers.SerializerMethodField()
    current_stage_id = serializers.SerializerMethodField()
    current_stage_name = serializers.SerializerMethodField()
    currentStageName = serializers.SerializerMethodField()
    current_stage_is_final = serializers.SerializerMethodField()
    # expose reference_no also as 'id' so the frontend can use item.id for perform-action URL
    id = serializers.SerializerMethodField()

    class Meta:
        model = DistributorPermitApplication
        fields = [
            'id',
            'reference_no',
            'applicant',
            'applicant_name',
            'supplier_company_name',
            'logistics_partner',
            'source_address',
            'origin',
            'destination',
            'route_details',
            'declaration_accepted',
            'is_excise_duty_fee_paid',
            'status',
            'officer_remarks',
            'submitted_at',
            'approval_date',
            'valid_up_to',
            'created_at',
            'updated_at',
            'line_items',
            'documents',
            'brand_count',
            'total_cases',
            'total_import_value',
            'total_education_cess',
            'total_additional_ed',
            'total_bulk_litres',
            'allowed_actions',
            'allowedActions',
            'current_stage_id',
            'current_stage_name',
            'currentStageName',
            'current_stage_is_final',
        ]
        read_only_fields = [
            'reference_no',
            'applicant',
            'status',
            'officer_remarks',
            'submitted_at',
            'created_at',
            'updated_at',
        ]

    def get_id(self, obj):
        return obj.reference_no

    def get_current_stage_id(self, obj):
        return getattr(obj.current_stage, 'id', None)

    def get_current_stage_name(self, obj):
        return getattr(obj.current_stage, 'name', '') or ''

    def get_currentStageName(self, obj):
        return self.get_current_stage_name(obj)

    def get_current_stage_is_final(self, obj):
        return bool(getattr(obj.current_stage, 'is_final', False))

    def to_internal_value(self, data):
        data = data.copy() if hasattr(data, 'copy') else dict(data)
        mappings = {
            'supplierCompanyName': 'supplier_company_name',
            'logisticsPartner': 'logistics_partner',
            'sourceAddress': 'source_address',
            'routeDetails': 'route_details',
            'declarationAccepted': 'declaration_accepted',
            'lineItems': 'line_items',
        }
        for camel, snake in mappings.items():
            if camel in data and snake not in data:
                data[snake] = data[camel]
        return super().to_internal_value(data)

    def validate(self, attrs):
        if not attrs.get('declaration_accepted'):
            raise serializers.ValidationError({'declaration_accepted': 'Declaration must be accepted.'})
        line_items = attrs.get('line_items') or []
        if not line_items:
            raise serializers.ValidationError({'line_items': 'At least one brand row is required.'})
        return attrs

    def create(self, validated_data):
        line_items = validated_data.pop('line_items', [])
        request = self.context.get('request')
        user = request.user if request else None
        raw_data = getattr(request, 'data', {}) or {}
        app_type = validated_data.pop('application_type', None) or raw_data.get('applicationType') or raw_data.get('application_type') or 'requisition'
        validated_data['applicant'] = user
        validated_data['status'] = DistributorPermitApplication.STATUS_SUBMITTED
        validated_data['submitted_at'] = timezone_now()
        validated_data['origin'] = validated_data.get('origin') or validated_data.get('source_address') or ''
        
        # Set initial workflow (15) and stage (148 - Forwarded Permit Section )
        try:
            from auth.workflow.models import WorkflowStage
            initial_stage = WorkflowStage.objects.filter(id=148).first()
            if initial_stage:
                validated_data['workflow_id'] = initial_stage.workflow_id
                validated_data['current_stage_id'] = 148
            else:
                validated_data['workflow_id'] = 15
                validated_data['current_stage_id'] = 148
        except Exception:
            validated_data['workflow_id'] = 15
            validated_data['current_stage_id'] = 148

        from django.db import transaction

        with transaction.atomic():
            application = DistributorPermitApplication.objects.create(
                reference_no=DistributorPermitApplication.generate_reference_no(app_type=app_type),
                **validated_data,
            )
            for item in line_items:
                self._create_line_item(application, item)
        return application

    def _create_line_item(self, application, item):
        brand = item['brand']
        size_ml = int(item['size_ml'])
        cases = int(item['cases'])
        brand_name = str(brand.brand_name or '').strip()
        rates = self._resolve_rates(brand_name, size_ml)
        pieces_per_case = self._resolve_pieces_per_case(size_ml)

        edp = rates['edp_per_case']
        import_fee = rates['import_pass_fee_per_case']
        mrp = rates['mrp_per_bottle']
        additional_ed = rates['additional_ed_per_case']
        education_cess = rates['education_cess_per_case']

        return DistributorPermitLineItem.objects.create(
            application=application,
            brand=brand,
            brand_name=brand_name,
            size_ml=size_ml,
            pieces_per_case=pieces_per_case,
            cases=cases,
            edp_per_case=edp,
            import_pass_fee_per_case=import_fee,
            mrp_per_bottle=mrp,
            additional_ed_per_case=additional_ed,
            education_cess_per_case=education_cess,
            total_import=import_fee * cases,
            total_education_cess=education_cess * cases,
            total_additional_ed=additional_ed * cases,
            bulk_litres=(Decimal(size_ml) * Decimal(pieces_per_case) * Decimal(cases) / Decimal('1000')),
        )

    def _resolve_rates(self, brand_name: str, size_ml: int) -> dict:
        row = (
            LiquorData.objects.filter(brand_name__iexact=brand_name, pack_size_ml=size_ml)
            .order_by('-updated_at', '-id')
            .first()
        )
        return {
            'edp_per_case': self._decimal(getattr(row, 'ex_factory_price_rs_per_case', 0)),
            'import_pass_fee_per_case': self._decimal(getattr(row, 'excise_duty_rs_per_case', 0)),
            'mrp_per_bottle': self._decimal(getattr(row, 'mrp_rs_per_bottle', 0)),
            'additional_ed_per_case': self._decimal(getattr(row, 'additional_excise_duty_rs_per_case', 0)),
            'education_cess_per_case': self._decimal(getattr(row, 'education_cess_rs_per_case', 0)),
        }

    def _resolve_pieces_per_case(self, size_ml: int) -> int:
        row = BrandMlInCases.objects.filter(ml=size_ml).order_by('id').first()
        return int(getattr(row, 'pieces_in_case', 0) or 0)

    def _decimal(self, value) -> Decimal:
        try:
            return Decimal(str(value or '0.00'))
        except Exception:
            return Decimal('0.00')

    def get_applicant_name(self, obj):
        user = getattr(obj, 'applicant', None)
        if not user:
            return ''
        full_name = ' '.join([
            str(getattr(user, 'first_name', '') or '').strip(),
            str(getattr(user, 'last_name', '') or '').strip(),
        ]).strip()
        return full_name or getattr(user, 'username', '') or getattr(user, 'email', '')

    def get_brand_count(self, obj):
        return obj.line_items.count()

    def get_total_cases(self, obj):
        return sum(int(item.cases or 0) for item in obj.line_items.all())

    def get_total_import_value(self, obj):
        val = sum((item.total_import or Decimal('0.00')) for item in obj.line_items.all())
        if not val or val <= Decimal('0.00'):
            return Decimal('1.00')
        return val

    def get_total_education_cess(self, obj):
        return sum((item.total_education_cess or Decimal('0.00')) for item in obj.line_items.all())

    def get_total_additional_ed(self, obj):
        return sum((item.total_additional_ed or Decimal('0.00')) for item in obj.line_items.all())

    def get_total_bulk_litres(self, obj):
        return sum((item.bulk_litres or Decimal('0.000')) for item in obj.line_items.all())

    def get_allowed_actions(self, obj):
        request = self.context.get('request')
        user = request.user if request else None
        if not user or not obj.current_stage:
            return []

        from auth.workflow.models import WorkflowTransition
        from models.transactional.supply_chain.access_control import transition_matches

        # If this application is at a final stage, no actions available
        if obj.current_stage.is_final:
            return []

        stage_id = obj.current_stage_id
        if stage_id == 154 or (obj.current_stage and 'PAYMENT' in str(obj.current_stage.name).upper()):
            if not obj.is_excise_duty_fee_paid:
                return ['PAY', 'FORCE_PAY']
            return []

        # The applicant (distributor/licensee who submitted the application):
        # - can SUBMIT when at the Pending (objection) stage 149
        if obj.applicant_id == getattr(user, 'id', None):
            if stage_id == 149:
                return ['SUBMIT']
            return []

        # For all admin roles: look up actual outgoing transitions from current stage
        # and filter to only those the current user's role can perform
        transitions = WorkflowTransition.objects.filter(
            workflow=obj.workflow,
            from_stage=obj.current_stage,
        ).exclude(
            condition__action='VIEW'
        ).select_related('to_stage')

        actions = []
        for t in transitions:
            cond = t.condition or {}
            cond_action = str(cond.get('action') or '').upper()
            if not cond_action or cond_action == 'VIEW':
                continue
            # Check if this user's role matches
            if transition_matches(t, user, cond_action):
                if cond_action not in actions:
                    actions.append(cond_action)

        return actions

    def get_allowedActions(self, obj):
        return self.get_allowed_actions(obj)


class DistributorSupplierSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    company_name = serializers.CharField()
    post = serializers.CharField(allow_blank=True)
    address = serializers.CharField()
    state = serializers.CharField(allow_blank=True)
    is_active = serializers.BooleanField(required=False)


class DistributorBrandMasterSerializer(serializers.Serializer):
    brand_id = serializers.IntegerField()
    brand_name = serializers.CharField()
    size_ml = serializers.IntegerField()
    pieces_per_case = serializers.IntegerField()
    edp_per_case = serializers.DecimalField(max_digits=15, decimal_places=2)
    import_pass_fee_per_case = serializers.DecimalField(max_digits=15, decimal_places=2)
    mrp_per_bottle = serializers.DecimalField(max_digits=15, decimal_places=2)
    additional_ed_per_case = serializers.DecimalField(max_digits=15, decimal_places=2)
    education_cess_per_case = serializers.DecimalField(max_digits=15, decimal_places=2)


def timezone_now():
    from django.utils import timezone

    return timezone.now()


class IMFLRevalidationActivationScheduleSerializer(serializers.ModelSerializer):
    class Meta:
        model = IMFLRevalidationActivationSchedule
        fields = '__all__'


class IMFLRevalidationSerializer(serializers.ModelSerializer):
    applicant_name = serializers.SerializerMethodField()
    distributor_permit_detail = DistributorPermitApplicationSerializer(source='distributor_permit', read_only=True)

    class Meta:
        model = IMFLRevalidation
        fields = '__all__'

    def get_applicant_name(self, obj):
        if not obj.applicant:
            return ''
        name = getattr(obj.applicant, 'get_full_name', lambda: '')() or obj.applicant.username
        return name.strip() or obj.applicant.username


class IMFLCancellationSerializer(serializers.ModelSerializer):
    applicant_name = serializers.SerializerMethodField()
    distributor_permit_detail = DistributorPermitApplicationSerializer(source='distributor_permit', read_only=True)

    class Meta:
        model = IMFLCancellation
        fields = '__all__'

    def get_applicant_name(self, obj):
        if not obj.applicant:
            return ''
        name = getattr(obj.applicant, 'get_full_name', lambda: '')() or obj.applicant.username
        return name.strip() or obj.applicant.username

