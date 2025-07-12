from rest_framework import serializers
from models.masters.core.models import District
from .state_serializer import StateSerializer  # Optional, if nesting

class DistrictSerializer(serializers.ModelSerializer):
    # Computed fields
    status = serializers.SerializerMethodField()
    state = serializers.CharField(source='state_code.state', read_only=True)

    class Meta:
        model = District
        fields = [
            'id',
            'district',
            'district_code',
            'state_code',
            'state',
            'is_active',
            'status',
            # 'subdivisions'  # Uncomment if using nested
        ]
        extra_kwargs = {
            'district_code': {
                'validators': []  # We'll handle this in validate
            },
            'state_code': {'read_only': True}  # Allow setting via ID
        }

    def validate_district_code(self, value):
        """Ensure district code is unique per state"""
        queryset = District.objects.filter(district_code=value)
        if self.instance:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise serializers.ValidationError("District code must be unique")
        return value

    def get_status(self, obj):
        return "Active" if obj.is_active else "Inactive"
