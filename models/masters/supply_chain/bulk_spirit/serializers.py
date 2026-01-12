from rest_framework import serializers
from .models import BulkSpiritType

class BulkSpiritTypeSerializer(serializers.ModelSerializer):
    
    class Meta:
        model = BulkSpiritType
        fields = ['sprit_id', 'bulk_spirit_kind_type', 'strength', 'price_bl', 'created_at', 'updated_at']
        read_only_fields = ['sprit_id', 'created_at', 'updated_at']

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        # Trim whitespace from string fields
        if representation.get('bulk_spirit_kind_type'):
            representation['bulk_spirit_kind_type'] = representation['bulk_spirit_kind_type'].strip()
        if representation.get('strength'):
            representation['strength'] = representation['strength'].strip()
        return representation
