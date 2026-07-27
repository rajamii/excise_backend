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

    class Meta:
        model = CompanyCollaboration
        fields = [
            # system
            'application_id',
            'workflow',
            'current_stage',
            'current_stage_name',
            'is_approved',
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
