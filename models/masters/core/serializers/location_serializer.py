from rest_framework import serializers
from models.masters.core.models import Location

class LocationSerializer(serializers.ModelSerializer):
    # Computed fields
    status = serializers.SerializerMethodField()
    district = serializers.CharField(source='district_code.district', read_only=True)

    class Meta:
        model = Location
        fields = [
            'id',
            'location_code',
            'location_description',
            'district_code',
            'district',
            'is_active',
            'status',
        ]
        extra_kwargs = {
            'location_code': {
                'validators': []  # Handled manually in validate
            }
        }

    def validate_location_code(self, value):
        """Ensure location code is unique per district"""
        queryset = Location.objects.filter(location_code=value)
        if self.instance:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise serializers.ValidationError("Location code must be unique")
        return value

    def get_status(self, obj):
        return "Active" if obj.is_active else "Inactive"
