from rest_framework import serializers
from .models import TransitPermitBottleType, BrandMlInCases

class TransitPermitBottleTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = TransitPermitBottleType
        fields = ['id', 'bottle_type', 'is_active']

class BrandMlInCasesSerializer(serializers.ModelSerializer):
    class Meta:
        model = BrandMlInCases
        fields = ['id', 'ml', 'pieces_in_case']
