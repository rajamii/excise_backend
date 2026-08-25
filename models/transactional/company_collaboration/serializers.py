from rest_framework import serializers

from auth.workflow.serializers import WorkflowObjectionSerializer, WorkflowTransactionSerializer

from .models import CompanyCollaboration


class CompanyCollaborationSerializer(serializers.ModelSerializer):
    # ── Read-only system / computed fields ───────────────────────────────
    application_id     = serializers.CharField(read_only=True)
    workflow           = serializers.PrimaryKeyRelatedField(read_only=True)
    current_stage      = serializers.PrimaryKeyRelatedField(read_only=True)
    current_stage_name = serializers.CharField(source='current_stage.name', read_only=True)
    is_approved        = serializers.BooleanField(read_only=True)
    allowed_actions    = serializers.SerializerMethodField()
    is_license_fee_paid = serializers.BooleanField(read_only=True)
    is_renewal          = serializers.BooleanField(read_only=True)
    is_paid             = serializers.BooleanField(read_only=True)
    applicant          = serializers.PrimaryKeyRelatedField(read_only=True)
    created_at         = serializers.DateTimeField(read_only=True)
    updated_at         = serializers.DateTimeField(read_only=True)
    valid_up_to        = serializers.SerializerMethodField()
    issued_license_id  = serializers.SerializerMethodField()

    # ── Nested audit trails (read-only) ──────────────────────────────────
    transactions = WorkflowTransactionSerializer(many=True, read_only=True)
    objections   = WorkflowObjectionSerializer(many=True, read_only=True)

    def get_allowed_actions(self, obj):
        request = self.context.get('request')
        if not request or not hasattr(request, 'user'):
            return []

        user = request.user
        role_name = getattr(getattr(user, 'role', None), 'name', '') or ''
        role_token = ''.join(ch for ch in str(role_name).lower() if ch.isalnum())

        current_stage = getattr(obj, 'current_stage', None)
        if not current_stage:
            return []

        from auth.workflow.models import WorkflowTransition
        from models.transactional.supply_chain.access_control import condition_role_matches

        transitions = WorkflowTransition.objects.filter(from_stage=current_stage)
        actions = []
        for t in transitions:
            cond = t.condition or {}
            if condition_role_matches(cond, user):
                action = cond.get('action')
                if action:
                    actions.append(str(action).strip().upper())

        if not actions:
            stage_name = str(getattr(current_stage, 'name', '') or '').lower()
            if not any(k in stage_name for k in ['approv', 'reject', 'issue', 'cancel']):
                if role_token in {'commissioner', 'jointcommissioner', 'level1', 'level2', 'level3', 'level4', 'level5', 'siteadmin'} or 'commissioner' in role_token:
                    actions = ['APPROVE', 'FORWARD', 'REJECT', 'RAISE_OBJECTION']
                else:
                    actions = ['FORWARD', 'REJECT', 'RAISE_OBJECTION']

        return list(set(actions))

    class Meta:
        model = CompanyCollaboration
        fields = [
            # system
            'application_id',
            'workflow',
            'current_stage',
            'current_stage_name',
            'is_approved',
            'allowed_actions',
            'is_license_fee_paid',
            'is_renewal',
            'is_paid',
            'applicant',
            'created_at',
            'updated_at',
            'valid_up_to',
            'issued_license_id',
            # year
            'financial_year',
            'application_year',
            # collaborating company (brand owner) — Step 2
            'brand_owner',
            'brand_owner_code',
            'brand_owner_name',
            'brand_owner_pan',
            'brand_owner_office_address',
            'brand_owner_factory_address',
            'brand_owner_mobile',
            'brand_owner_email',
            # bottler / licensee — Step 1
            'licensee_name',
            'licensee_address',
            'license_number',
            # brands / fees — Step 3
            'selected_brand_ids',
            'selected_brands',
            'fee_structure',
            'overview_summary',
            'undertaking',
            # audit trails
            'transactions',
            'objections',
        ]
        read_only_fields = [
            'application_id',
            'workflow',
            'current_stage',
            'current_stage_name',
            'is_approved',
            'is_license_fee_paid',
            'is_renewal',
            'is_paid',
            'applicant',
            'financial_year',
            'created_at',
            'updated_at',
        ]

    # ── Field-level validation ────────────────────────────────────────────

    def validate_brand_owner_mobile(self, value):
        if not value:
            return value
        digits = ''.join(filter(str.isdigit, str(value)))
        if digits and not (7 <= len(digits) <= 15):
            raise serializers.ValidationError(
                'Mobile number must contain between 7 and 15 digits.'
            )
        return value

    def validate_selected_brand_ids(self, value):
        if value is None:
            return []
        if not isinstance(value, list):
            raise serializers.ValidationError('selected_brand_ids must be a list.')
        return value

    def validate_selected_brands(self, value):
        if value is None:
            return []
        if not isinstance(value, list):
            raise serializers.ValidationError('selected_brands must be a list.')
        return value

    def get_valid_up_to(self, obj):
        try:
            from django.contrib.contenttypes.models import ContentType
            from models.masters.license.models import License
            ct = ContentType.objects.get_for_model(obj)
            license_obj = License.objects.filter(source_content_type=ct, source_object_id=obj.pk).first()
            if license_obj and license_obj.valid_up_to:
                return license_obj.valid_up_to.isoformat()
        except Exception:
            pass
        return None

    def get_issued_license_id(self, obj):
        try:
            from django.contrib.contenttypes.models import ContentType
            from models.masters.license.models import License
            ct = ContentType.objects.get_for_model(obj)
            license_obj = License.objects.filter(source_content_type=ct, source_object_id=obj.pk).first()
            if license_obj:
                return license_obj.license_id
        except Exception:
            pass
        return None
