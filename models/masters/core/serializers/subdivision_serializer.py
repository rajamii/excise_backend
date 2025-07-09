from rest_framework import serializers
from django.core.validators import MinValueValidator, MaxValueValidator
from models.masters.core.models import Subdivision
from django.utils import timezone

class SubdivisionSerializer(serializers.ModelSerializer):
    # Computed fields
    status = serializers.SerializerMethodField()
    district_name = serializers.CharField(source='DistrictCode.District', read_only=True)
    
    class Meta:
        model = Subdivision
        fields = [
            'id',
            'SubDivisionName',
            'SubDivisionNameLL',
            'SubDivisionCode',
            'DistrictCode',
            'district_name',
            'IsActive',
            'status'
        ]
        extra_kwargs = {
            'SubDivisionCode': {
                'validators': [
                    MinValueValidator(1000),
                    MaxValueValidator(9999)
                ]
            },
            'SubDivisionNameLL': {
                'required': True,
                'allow_blank': False
            }
        }

    def get_police_station_count(self, obj) -> int:
        """Safely get count of related police stations"""
        return obj.police_stations.count() if hasattr(obj, 'police_stations') else 0

    # Field validation
    def validate_SubDivisionCode(self, value):
        queryset = Subdivision.objects.filter(SubDivisionCode=value)
        if self.instance:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise serializers.ValidationError("Subdivision code must be unique")
        return value

    def validate_SubDivisionNameLL(self, value):
        value = value.strip()
        if len(value) < 2:
            raise serializers.ValidationError("Local name must be ≥2 characters")
        return value

    # Object validation
    def validate(self, attrs):
        if 'SubDivisionName' in attrs and 'SubDivisionNameLL' in attrs:
            if attrs['SubDivisionName'].lower() == attrs['SubDivisionNameLL'].lower():
                raise serializers.ValidationError(
                    "Name and local name cannot be identical"
                )
        attrs['last_modified'] = timezone.now()
        return attrs

    # Computed field
    def get_status(self, obj):
        return "Active" if obj.IsActive else "Inactive"
