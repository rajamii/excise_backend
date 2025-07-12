from rest_framework import serializers
from ...core import models as master_models
from ..helper import ROAD_TYPE_CHOICES

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