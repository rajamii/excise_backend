from rest_framework import serializers
from ..models import AdditionalChargeConfig

class AdditionalChargeConfigSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.license_category', read_only=True)
    
    class Meta:
        model = AdditionalChargeConfig
        fields = ['id', 'category', 'category_name', 'charge_type', 'is_active']
