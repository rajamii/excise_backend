from rest_framework import serializers
from .models import BrandMlInCases
from models.masters.supply_chain.liquor_data.models import MasterBottleType

class TransitPermitBottleTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = MasterBottleType
        fields = ['id', 'bottle_type', 'is_active']

class BrandMlInCasesSerializer(serializers.ModelSerializer):
    class Meta:
        model = BrandMlInCases
        fields = ['id', 'ml', 'pieces_in_case']
