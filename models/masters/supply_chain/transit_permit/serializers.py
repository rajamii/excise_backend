from rest_framework import serializers
from .models import TransitPermitBottleType

class TransitPermitBottleTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = TransitPermitBottleType
        fields = ['id', 'bottle_type', 'is_active']
