from rest_framework import serializers
from models.masters.core.models import Ward, Location


class WardSerializer(serializers.ModelSerializer):
    """
    Serializer for Ward model.
    """
    # Computed fields
    status = serializers.SerializerMethodField()
    location_description = serializers.CharField(
        source='location_code.location_description',
        read_only=True
    )
    district_name = serializers.CharField(
        source='location_code.district_code.district',
        read_only=True
    )
    created_by_username = serializers.CharField(
        source='created_by.username',
        read_only=True
    )

    class Meta:
        model = Ward
        fields = [
            'id',
            'ward_name',
            'ward_number',
            'location_code',
            'location_description',
            'district_name',
            'population',
            'area_sq_km',
            'is_active',
            'status',
            'created_by',
            'created_by_username',
            'operation_date',
        ]
        read_only_fields = ['id', 'operation_date', 'created_by']

    def get_status(self, obj):
        """Return status string based on is_active field"""
        return "Active" if obj.is_active else "Inactive"

    def validate_ward_number(self, value):
        """Validate that ward number is positive"""
        if value <= 0:
            raise serializers.ValidationError("Ward number must be positive.")
        return value

    def validate_population(self, value):
        """Validate population if provided"""
        if value is not None and value < 0:
            raise serializers.ValidationError("Population cannot be negative.")
        return value

    def validate_area_sq_km(self, value):
        """Validate area if provided"""
        if value is not None and value <= 0:
            raise serializers.ValidationError("Area must be positive.")
        return value

    def validate(self, data):
        """
        Validate that the ward number is unique within its location.
        """
        location_code = data.get('location_code')
        ward_number = data.get('ward_number')

        if location_code and ward_number:
            queryset = Ward.objects.filter(
                location_code=location_code,
                ward_number=ward_number
            )
            
            # During updates, exclude current instance
            if self.instance:
                queryset = queryset.exclude(pk=self.instance.pk)
            
            if queryset.exists():
                raise serializers.ValidationError({
                    'ward_number': f'Ward number {ward_number} already exists in this location.'
                })

        return data

    def create(self, validated_data):
        """Custom create with audit logging"""
        request = self.context.get('request')
        if request and hasattr(request, 'user'):
            validated_data['created_by'] = request.user
        return super().create(validated_data)
