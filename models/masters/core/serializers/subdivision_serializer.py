from rest_framework import serializers
from django.core.validators import MinValueValidator, MaxValueValidator
from models.masters.core.models import Subdivision
from django.utils import timezone

class SubdivisionSerializer(serializers.ModelSerializer):
    # Computed fields
    status = serializers.SerializerMethodField()
    district = serializers.CharField(source='district_code.district', read_only=True)

    class Meta:
        model = Subdivision
        fields = [
            'id',
            'subdivision',
            'subdivision_code',
            'district_code',
            'district',
            'is_active',
            'status'
        ]
        extra_kwargs = {
            'subdivision_code': {
                'validators': [
                    MinValueValidator(1000),
                    MaxValueValidator(9999)
                ]
            }
        }

    # Computed field
    def get_status(self, obj):
        return "Active" if obj.is_active else "Inactive"

    # Optional: related object count
    def get_police_station_count(self, obj) -> int:
        return obj.police_stations.count() if hasattr(obj, 'police_stations') else 0

    # Field validation
    def validate_subdivision_code(self, value):
        queryset = Subdivision.objects.filter(subdivision_code=value)
        if self.instance:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise serializers.ValidationError("Subdivision code must be unique")
        return value
""" 
    # Object-level validation
    def validate(self, attrs):
        attrs['last_modified'] = timezone.now()
        return attrs """
