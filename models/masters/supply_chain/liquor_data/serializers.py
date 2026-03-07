from rest_framework import serializers
from .models import LiquorData

class LiquorDataSerializer(serializers.ModelSerializer):
    class Meta:
        model = LiquorData
        fields = ['id', 'brand_name', 'pack_size_ml','education_cess_rs_per_case',
            'excise_duty_rs_per_case',
            'additional_excise_duty_rs_per_case',]

class BrandSizeSerializer(serializers.Serializer):
    brand_name = serializers.CharField()
    sizes = serializers.ListField(child=serializers.IntegerField())
    
    def to_representation(self, instance):
        return {
            'brand_name': instance['brand_name'],
            'sizes': instance['sizes']
        }

class ApprovedBrandDetailsSerializer(serializers.Serializer):
    """Read-only serializer for approved brand details"""
    id = serializers.IntegerField(read_only=True)
    brandName = serializers.CharField(source='brand_details', read_only=True)
    liquorType = serializers.CharField(source='brand_type', read_only=True)
    bottleSize = serializers.IntegerField(source='capacity_size', read_only=True)
    manufacturingUnit = serializers.CharField(source='distillery_name', read_only=True)

class BottleTypeSerializer(serializers.Serializer):
    """Read-only serializer for bottle types"""
    id = serializers.IntegerField(read_only=True)
    bottleType = serializers.CharField(source='bottle_type', read_only=True)
