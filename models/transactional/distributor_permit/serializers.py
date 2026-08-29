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
    IMFLArrival,
    IMFLCasesProcessed,
    IMFLBrandWarehouse,
)


class DistributorPermitLineItemSerializer(serializers.ModelSerializer):
    brand_id = serializers.IntegerField(write_only=True)
    brand_master_id = serializers.IntegerField(source='brand_id', read_only=True)
    cases = serializers.IntegerField(write_only=True, required=False, default=1)

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
            'permit_number',
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

    def validate_brand_id(self, value):
        from .models import IMFLBrand
        from models.masters.supply_chain.liquor_data.models import MasterBrandList

        if IMFLBrand.objects.filter(id=value).exists() or MasterBrandList.objects.filter(id=value).exists():
            return value
        raise serializers.ValidationError(f'Invalid brand ID "{value}" - brand does not exist.')

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
            'permit_wise_details',
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
            self._process_and_save_line_items(application, line_items)
        return application

    def _process_and_save_line_items(self, application, line_items):
        from .models import IMFLBrand
        from models.masters.supply_chain.liquor_data.models import MasterBrandList

        expanded_items = []
        for item in line_items:
            raw_brand_id = item.get('brand_id')
            imfl_brand = IMFLBrand.objects.filter(id=raw_brand_id).first() if raw_brand_id else None
            master_brand = MasterBrandList.objects.filter(id=raw_brand_id).first() if raw_brand_id else None

            brand = master_brand
            if imfl_brand:
                brand_name = str(imfl_brand.brand_name or '').strip()
                size_ml = int(item.get('size_ml') or imfl_brand.size_ml or 750)
                pieces_per_case = int(item.get('pieces_per_case') or imfl_brand.pieces_per_case or self._resolve_pieces_per_case(size_ml))
            elif master_brand:
                brand_name = str(getattr(master_brand, 'brand_name', '') or '').strip()
                size_ml = int(item.get('size_ml') or 750)
                pieces_per_case = int(item.get('pieces_per_case') or self._resolve_pieces_per_case(size_ml))
            else:
                brand_name = str(item.get('brand_name') or 'IMFL Brand').strip()
                size_ml = int(item.get('size_ml') or 750)
                pieces_per_case = int(item.get('pieces_per_case') or self._resolve_pieces_per_case(size_ml))

            cases = int(item.get('cases') or 1)
            rates = self._resolve_rates(brand_name, size_ml)

            edp = self._decimal(item.get('edp_per_case') or item.get('edp') or (imfl_brand.edp_per_case if imfl_brand else 0))
            if edp <= Decimal('0.00'):
                edp = rates['edp_per_case']

            import_fee = self._decimal(item.get('import_pass_fee_per_case') or item.get('import_fee'))
            if import_fee <= Decimal('0.00'):
                import_fee = rates['import_pass_fee_per_case']

            mrp = self._decimal(item.get('mrp_per_bottle') or item.get('mrp'))
            if mrp <= Decimal('0.00'):
                mrp = rates['mrp_per_bottle']

            additional_ed = self._decimal(item.get('additional_ed_per_case') or item.get('additional_ed'))
            if additional_ed <= Decimal('0.00'):
                additional_ed = rates['additional_ed_per_case']

            education_cess = self._decimal(item.get('education_cess_per_case') or item.get('education_cess'))
            if education_cess <= Decimal('0.00'):
                education_cess = rates['education_cess_per_case']

            expanded_items.append({
                'brand': brand,
                'brand_name': brand_name,
                'size_ml': size_ml,
                'cases': cases,
                'pieces_per_case': pieces_per_case,
                'edp': edp,
                'import_fee': import_fee,
                'mrp': mrp,
                'additional_ed': additional_ed,
                'education_cess': education_cess,
            })

        permits = []
        current_permit_index = 1
        current_permit_cases = 0
        current_permit_items = []

        for item in expanded_items:
            rem_cases = item['cases']
            while rem_cases > 0:
                available_space = 700 - current_permit_cases
                if available_space <= 0:
                    permits.append((current_permit_index, current_permit_items))
                    current_permit_index += 1
                    current_permit_cases = 0
                    current_permit_items = []
                    available_space = 700

                allocated_cases = min(rem_cases, available_space)

                sub_item = dict(item)
                sub_item['allocated_cases'] = allocated_cases
                sub_item['permit_number'] = f"{application.reference_no}-P{current_permit_index}"
                current_permit_items.append(sub_item)

                current_permit_cases += allocated_cases
                rem_cases -= allocated_cases

        if current_permit_items:
            permits.append((current_permit_index, current_permit_items))

        permit_wise_details = []
        for seq_num, items in permits:
            p_num = f"{application.reference_no}-P{seq_num}"
            p_cases = sum(i['allocated_cases'] for i in items)
            p_import_fee = sum(i['import_fee'] * i['allocated_cases'] for i in items)
            p_additional_ed = sum(i['additional_ed'] * i['allocated_cases'] for i in items)
            p_edu_cess = sum(i['education_cess'] * i['allocated_cases'] for i in items)
            p_bl = sum((Decimal(i['size_ml']) * Decimal(i['pieces_per_case']) * Decimal(i['allocated_cases']) / Decimal('1000')) for i in items)

            permit_wise_details.append({
                'permit_number': p_num,
                'permit_sequence': seq_num,
                'total_cases': p_cases,
                'total_import_fee': float(p_import_fee),
                'total_additional_ed': float(p_additional_ed),
                'total_education_cess': float(p_edu_cess),
                'total_bulk_litres': float(p_bl),
                'line_items': [
                    {
                        'brand_id': getattr(i['brand'], 'id', i['brand']),
                        'brand_name': i['brand_name'],
                        'size_ml': i['size_ml'],
                        'pieces_per_case': i['pieces_per_case'],
                        'cases': i['allocated_cases'],
                        'edp_per_case': float(i['edp']),
                        'import_pass_fee_per_case': float(i['import_fee']),
                        'total_import': float(i['import_fee'] * i['allocated_cases']),
                        'additional_ed_per_case': float(i['additional_ed']),
                        'total_additional_ed': float(i['additional_ed'] * i['allocated_cases']),
                        'education_cess_per_case': float(i['education_cess']),
                        'total_education_cess': float(i['education_cess'] * i['allocated_cases']),
                        'mrp_per_bottle': float(i['mrp']),
                        'bulk_litres': float(Decimal(i['size_ml']) * Decimal(i['pieces_per_case']) * Decimal(i['allocated_cases']) / Decimal('1000')),
                        'permit_number': p_num,
                    } for i in items
                ]
            })

            for i in items:
                DistributorPermitLineItem.objects.create(
                    application=application,
                    brand=i['brand'],
                    brand_name=i['brand_name'],
                    size_ml=i['size_ml'],
                    pieces_per_case=i['pieces_per_case'],
                    edp_per_case=i['edp'],
                    import_pass_fee_per_case=i['import_fee'],
                    mrp_per_bottle=i['mrp'],
                    additional_ed_per_case=i['additional_ed'],
                    education_cess_per_case=i['education_cess'],
                    permit_number=p_num,
                )

        application.permit_wise_details = permit_wise_details
        application.save(update_fields=['permit_wise_details'])

    def _resolve_rates(self, brand_name: str, size_ml: int) -> dict:
        prefix = brand_name.split(' - ')[0].strip() if ' - ' in brand_name else brand_name
        row = (
            LiquorData.objects.filter(brand_name__iexact=brand_name, pack_size_ml=size_ml)
            .order_by('-updated_at', '-id')
            .first()
        )
        if not row:
            row = (
                LiquorData.objects.filter(brand_name__icontains=prefix, pack_size_ml=size_ml)
                .order_by('-updated_at', '-id')
                .first()
            )

        edp = self._decimal(getattr(row, 'ex_factory_price_rs_per_case', 0))
        import_fee = self._decimal(getattr(row, 'excise_duty_rs_per_case', 0))
        mrp = self._decimal(getattr(row, 'mrp_rs_per_bottle', 0))
        add_ed = self._decimal(getattr(row, 'additional_excise_duty_rs_per_case', 0))
        edu_cess = self._decimal(getattr(row, 'education_cess_rs_per_case', 0))

        if import_fee <= Decimal('0.00'):
            import_fee = Decimal('1400.00')
        if add_ed <= Decimal('0.00'):
            add_ed = Decimal('350.00')
        if edp <= Decimal('0.00'):
            edp = Decimal('5800.00')
        if edu_cess <= Decimal('0.00'):
            edu_cess = Decimal('60.00')
        if mrp <= Decimal('0.00'):
            mrp = Decimal('850.00')

        return {
            'edp_per_case': edp,
            'import_pass_fee_per_case': import_fee,
            'mrp_per_bottle': mrp,
            'additional_ed_per_case': add_ed,
            'education_cess_per_case': edu_cess,
        }

    def _resolve_pieces_per_case(self, size_ml: int) -> int:
        row = BrandMlInCases.objects.filter(ml=size_ml).order_by('id').first()
        pieces = int(getattr(row, 'pieces_in_case', 0) or 0)
        if pieces <= 0:
            if size_ml == 750: return 12
            elif size_ml == 375: return 24
            elif size_ml == 180: return 48
            return 12
        return pieces

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
        if obj.permit_wise_details:
            return sum(int(p.get('total_cases', 0) or 0) for p in obj.permit_wise_details)
        return 0

    def get_total_import_value(self, obj):
        if obj.permit_wise_details:
            val = Decimal(str(sum(float(p.get('total_import_fee', 0.0) or 0.0) for p in obj.permit_wise_details)))
            if val > Decimal('0.00'):
                return val
        return Decimal('1.00')

    def get_total_education_cess(self, obj):
        if obj.permit_wise_details:
            return Decimal(str(sum(float(p.get('total_education_cess', 0.0) or 0.0) for p in obj.permit_wise_details)))
        return Decimal('0.00')

    def get_total_additional_ed(self, obj):
        if obj.permit_wise_details:
            return Decimal(str(sum(float(p.get('total_additional_ed', 0.0) or 0.0) for p in obj.permit_wise_details)))
        return sum((getattr(item, 'total_additional_ed', Decimal('0.00')) or Decimal('0.00')) for item in obj.line_items.all())

    def get_total_bulk_litres(self, obj):
        if obj.permit_wise_details:
            return Decimal(str(sum(float(p.get('total_bulk_litres', 0.0) or 0.0) for p in obj.permit_wise_details)))
        return sum((getattr(item, 'bulk_litres', Decimal('0.000')) or Decimal('0.000')) for item in obj.line_items.all())

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
    distributor_permit_ref_no = serializers.SerializerMethodField()
    distributorPermitRefNo = serializers.SerializerMethodField()
    allowed_actions = serializers.SerializerMethodField()
    allowedActions = serializers.SerializerMethodField()

    class Meta:
        model = IMFLRevalidation
        fields = '__all__'
        read_only_fields = ('reference_no', 'applicant', 'submitted_at', 'workflow', 'current_stage', 'status')

    def get_distributor_permit_ref_no(self, obj):
        if obj.distributor_permit:
            return str(obj.distributor_permit.reference_no)
        return ''

    def get_distributorPermitRefNo(self, obj):
        return self.get_distributor_permit_ref_no(obj)

    def get_applicant_name(self, obj):
        if not obj.applicant:
            return ''
        name = getattr(obj.applicant, 'get_full_name', lambda: '')() or obj.applicant.username
        return name.strip() or obj.applicant.username

    def get_allowed_actions(self, obj):
        request = self.context.get('request')
        user = getattr(request, 'user', None) if request else None
        if not user or not user.is_authenticated:
            return []

        from auth.workflow.services import WorkflowService
        from models.transactional.supply_chain.access_control import transition_matches

        if not obj.workflow or not obj.current_stage:
            return []

        transitions = WorkflowService.get_next_stages(obj)
        actions = []
        for t in transitions:
            cond = t.condition or {}
            cond_action = str(cond.get('action') or '').upper()
            if not cond_action or cond_action == 'VIEW':
                continue
            if transition_matches(t, user, cond_action):
                if cond_action not in actions:
                    actions.append(cond_action)

        role_name = str(getattr(getattr(user, 'role', None), 'name', '') or '').lower()
        role_id = getattr(getattr(user, 'role', None), 'id', 0)
        is_officer_or_admin = (
            'commissioner' in role_name or
            'admin' in role_name or
            'officer' in role_name or
            'permit' in role_name or
            getattr(user, 'is_superuser', False) or
            getattr(user, 'is_staff', False) or
            role_id in (5, 6, 7, 9, 10, 12, 14)
        )
        if is_officer_or_admin:
            stage_id = getattr(obj.current_stage, 'id', None)
            if stage_id in (160, 161) or 'COMMISSIONER' in str(obj.status or '').upper() or 'FORWARDED' in str(obj.status or '').upper():
                if 'APPROVE' not in actions:
                    actions.append('APPROVE')

        # Remove REJECT action for IMFL Revalidation
        actions = [a for a in actions if a.upper() != 'REJECT']

        return actions

    def get_allowedActions(self, obj):
        return self.get_allowed_actions(obj)


class IMFLCancellationSerializer(serializers.ModelSerializer):
    applicant_name = serializers.SerializerMethodField()
    distributor_permit_detail = DistributorPermitApplicationSerializer(source='distributor_permit', read_only=True)
    allowed_actions = serializers.SerializerMethodField()
    allowedActions = serializers.SerializerMethodField()

    class Meta:
        model = IMFLCancellation
        fields = '__all__'
        read_only_fields = ('reference_no', 'applicant', 'submitted_at', 'workflow', 'current_stage', 'status')

    def get_applicant_name(self, obj):
        if not obj.applicant:
            return ''
        name = getattr(obj.applicant, 'get_full_name', lambda: '')() or obj.applicant.username
        return name.strip() or obj.applicant.username

    def get_allowed_actions(self, obj):
        request = self.context.get('request')
        user = getattr(request, 'user', None) if request else None
        if not user or not user.is_authenticated:
            return []

        from auth.workflow.services import WorkflowService
        from models.transactional.supply_chain.access_control import transition_matches

        if not obj.workflow or not obj.current_stage:
            return []

        transitions = WorkflowService.get_next_stages(obj)
        actions = []
        for t in transitions:
            cond = t.condition or {}
            cond_action = str(cond.get('action') or '').upper()
            if not cond_action or cond_action == 'VIEW':
                continue
            if transition_matches(t, user, cond_action):
                if cond_action not in actions:
                    actions.append(cond_action)

        role_name = str(getattr(getattr(user, 'role', None), 'name', '') or '').lower()
        role_id = getattr(getattr(user, 'role', None), 'id', 0)
        is_officer_or_admin = (
            'commissioner' in role_name or
            'admin' in role_name or
            'officer' in role_name or
            'permit' in role_name or
            getattr(user, 'is_superuser', False) or
            getattr(user, 'is_staff', False) or
            role_id in (5, 6, 7, 9, 10, 12, 14)
        )
        if is_officer_or_admin:
            stage_id = getattr(obj.current_stage, 'id', None)
            if stage_id in (162, 163) or 'COMMISSIONER' in str(obj.status or '').upper() or 'FORWARDED' in str(obj.status or '').upper():
                if 'APPROVE' not in actions:
                    actions.append('APPROVE')
                actions = [a for a in actions if a != 'REJECT']

        return actions

    def get_allowedActions(self, obj):
        return self.get_allowed_actions(obj)


class IMFLArrivalSerializer(serializers.ModelSerializer):
    arrived_by_name = serializers.SerializerMethodField()

    class Meta:
        model = IMFLArrival
        fields = '__all__'
        read_only_fields = ('arrived_by', 'arrived_at', 'created_at', 'updated_at')

    def get_arrived_by_name(self, obj):
        if not obj.arrived_by:
            return ''
        name = getattr(obj.arrived_by, 'get_full_name', lambda: '')() or obj.arrived_by.username
        return name.strip() or obj.arrived_by.username


class IMFLCasesProcessedSerializer(serializers.ModelSerializer):
    submitted_by_name = serializers.SerializerMethodField()
    oic_officer_name = serializers.SerializerMethodField()
    application_ref = serializers.CharField(source='distributor_permit.reference_no', read_only=True)

    class Meta:
        model = IMFLCasesProcessed
        fields = '__all__'
        read_only_fields = ('submitted_by', 'submitted_at', 'reviewed_at', 'created_at', 'updated_at')

    def get_submitted_by_name(self, obj):
        if not obj.submitted_by:
            return ''
        name = getattr(obj.submitted_by, 'get_full_name', lambda: '')() or obj.submitted_by.username
        return name.strip() or obj.submitted_by.username

    def get_oic_officer_name(self, obj):
        if not obj.oic_officer:
            return ''
        name = getattr(obj.oic_officer, 'get_full_name', lambda: '')() or obj.oic_officer.username
        return name.strip() or obj.oic_officer.username


class IMFLBrandWarehouseSerializer(serializers.ModelSerializer):
    officer_in_charge_name = serializers.SerializerMethodField()
    application_ref = serializers.CharField(source='distributor_permit.reference_no', read_only=True)
    pieces_in_case = serializers.IntegerField(source='pieces_per_case', read_only=True)

    class Meta:
        model = IMFLBrandWarehouse
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at')

    def get_officer_in_charge_name(self, obj):
        if not obj.officer_in_charge:
            return ''
        name = getattr(obj.officer_in_charge, 'get_full_name', lambda: '')() or obj.officer_in_charge.username
        return name.strip() or obj.officer_in_charge.username



