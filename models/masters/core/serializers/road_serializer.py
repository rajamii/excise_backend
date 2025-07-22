from rest_framework import serializers
from ...core import models as master_models
from ..helper import ROAD_TYPE_CHOICES

class RoadSerializer(serializers.ModelSerializer):
    district = serializers.PrimaryKeyRelatedField(
        queryset=master_models.District.objects.all()
    )

    class Meta:
        model = master_models.Road
        fields = ['id', 'road_name', 'road_type', 'district']

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation['district'] = {
            'id': instance.district.id,
            'district': instance.district.district,
            'districtCode': instance.district.district_code
        }
        return representation

    def validate_road_type(self, value):
        valid_choices = [choice[0] for choice in ROAD_TYPE_CHOICES]
        if value not in valid_choices:
            raise serializers.ValidationError(
                f"Invalid road type. Must be one of: {', '.join(valid_choices)}"
            )
        return value