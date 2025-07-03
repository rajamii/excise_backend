from rest_framework import serializers
from masters import models as master_models

class DistrictSerializer(serializers.ModelSerializer):
    state = serializers.CharField(source='state_code.state', read_only=True)

    class Meta: 
        model = master_models.District
        fields = '__all__'  # Corrected from '_all_'

class SubDivisonSerializer(serializers.ModelSerializer):
    district = serializers.CharField(source='district_code.district', read_only=True)

    class Meta: 
        model = master_models.Subdivision
        fields = '__all__'  # Corrected from '_all_'

class PoliceStationSerializer(serializers.ModelSerializer):
    subdivision = serializers.CharField(source='subdivision_code.subdivision', read_only=True)
    district = serializers.CharField(source='subdivision_code.district_code.district', read_only=True)

    class Meta: 
        model = master_models.PoliceStation
        fields = '__all__'  # Corrected from '_all_'

class LicenseCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = master_models.LicenseCategory
        fields = [
            'id',
            'license_category',
        ]

class LicenseTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = master_models.LicenseType
        fields = [
            'id',
            'license_type',
        ]