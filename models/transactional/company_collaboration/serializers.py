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
    applicant          = serializers.PrimaryKeyRelatedField(read_only=True)
    created_at         = serializers.DateTimeField(read_only=True)
    updated_at         = serializers.DateTimeField(read_only=True)

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
            'applicant',
            'created_at',
            'updated_at',
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
