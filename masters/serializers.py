from rest_framework import serializers
from masters import models as master_models
from .helper import ROAD_TYPE_CHOICES

class DistrictSerializer(serializers.ModelSerializer):
    state = serializers.CharField(source='state_code.state', read_only=True)

    class Meta:
        model = master_models.District
        fields = '__all__'

class SubdivisionSerializer(serializers.ModelSerializer):
    district = serializers.CharField(source='district_code.district', read_only=True)

    class Meta:
        model = master_models.Subdivision
        fields = '__all__'

class PoliceStationSerializer(serializers.ModelSerializer):
    subdivision = serializers.CharField(source='subdivision_code.subdivision', read_only=True)
    district = serializers.CharField(source='subdivision_code.district_code.district', read_only=True)

    class Meta:
        model = master_models.PoliceStation
        fields = '__all__'

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

class LicenseTitleSerializer(serializers.ModelSerializer):
    class Meta:
        model = master_models.LicenseTitle
        fields = [
            'id',
            'description',
        ]

class LicenseSubcategorySerializer(serializers.ModelSerializer):
    category = serializers.PrimaryKeyRelatedField(queryset=master_models.LicenseCategory.objects.all())

    class Meta:
        model = master_models.LicenseSubcategory
        fields = ['id', 'description', 'category']

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation['category'] = instance.category.license_category if instance.category else None
        return representation

class RoadSerializer(serializers.ModelSerializer):
    district = serializers.CharField(source='district_id.district', read_only=True)

    class Meta:
        model = master_models.Road
        fields = ['id', 'road_name', 'district_id', 'district', 'road_type']

    def validate_road_type(self, value):
        valid_choices = [choice[0] for choice in ROAD_TYPE_CHOICES]
        if value not in valid_choices:
            raise serializers.ValidationError(
                f"Invalid road type. Must be one of: {', '.join(valid_choices)}"
            )
        return value