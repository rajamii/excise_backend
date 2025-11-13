from rest_framework import serializers
from .models import BulkSpiritType

class BulkSpiritTypeSerializer(serializers.ModelSerializer):
    
    class Meta:
        model = BulkSpiritType
        fields = ['sprit_id', 'strength_from', 'strength_to', 'price_bl', 'created_at', 'updated_at']
        read_only_fields = ['sprit_id', 'created_at', 'updated_at']
