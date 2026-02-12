from rest_framework import serializers
from django.utils import timezone
from ..models import LicenseeProfile

# Fields that are set once at creation and must never change afterwards
IMMUTABLE_FIELDS = ('father_name', 'dob', 'gender', 'nationality')


class LicenseeProfileSerializer(serializers.ModelSerializer):

    # ── Display fields ────────────────────────────────────────────
    gender_display             = serializers.CharField(source='get_gender_display',             read_only=True)
    marital_status_display     = serializers.CharField(source='get_marital_status_display',     read_only=True)
    residential_status_display = serializers.CharField(source='get_residential_status_display', read_only=True)
    created_by_username        = serializers.CharField(source='created_by.username',            read_only=True)

    class Meta:
        model  = LicenseeProfile
        fields = [
            'id',
            'father_name',
            'dob',
            'gender',
            'gender_display',
            'nationality',
            'marital_status',
            'marital_status_display',
            'residential_status',
            'residential_status_display',
            'created_by',
            'created_by_username',
            'operation_date',
        ]
        read_only_fields = ['id', 'operation_date', 'created_by']

    # ── Field-level validation ────────────────────────────────────

    def validate_dob(self, value):
        if value >= timezone.now().date():
            raise serializers.ValidationError("Date of birth must be a past date.")
        return value

    def validate_father_name(self, value):
        return ' '.join(value.strip().split())

    # ── Object-level validation ───────────────────────────────────

    def validate(self, data):
        """
        Block any attempt to change immutable fields during an update.
        Works for both PUT (full update) and PATCH (partial update).
        """
        if self.instance is not None:
            attempted_changes = [
                field for field in IMMUTABLE_FIELDS
                if field in data and str(getattr(self.instance, field)) != str(data[field])
            ]
            if attempted_changes:
                raise serializers.ValidationError({
                    field: f"'{field}' cannot be changed after the profile is created."
                    for field in attempted_changes
                })
        return data

    # ── Custom save logic ─────────────────────────────────────────

    def create(self, validated_data):
        request = self.context.get('request')
        if request and hasattr(request, 'user'):
            validated_data['created_by'] = request.user
        return super().create(validated_data)

    def update(self, instance, validated_data):
        # Strip immutable fields — safety net so they can never be overwritten
        for field in IMMUTABLE_FIELDS:
            validated_data.pop(field, None)
        return super().update(instance, validated_data)