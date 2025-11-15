from rest_framework import serializers
from .models import LiquorData

class LiquorDataSerializer(serializers.ModelSerializer):
    class Meta:
        model = LiquorData
        fields = ['id', 'brand_name', 'pack_size_ml']

class BrandSizeSerializer(serializers.Serializer):
    brand_name = serializers.CharField()
    sizes = serializers.ListField(child=serializers.IntegerField())
    
    def to_representation(self, instance):
        return {
            'brand_name': instance['brand_name'],
            'sizes': instance['sizes']
        }