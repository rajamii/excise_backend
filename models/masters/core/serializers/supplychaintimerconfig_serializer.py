import re
from rest_framework import serializers
from models.masters.core.models import SupplyChainTimerConfig

class SupplyChainTimerConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = SupplyChainTimerConfig
        fields = [
            'id', 
            'code', 
            'description', 
            'delay_value', 
            'delay_unit', 
            'is_active', 
            'created_at', 
            'updated_at', 
            'validity_period_days'
        ]
        read_only_fields = ['id', 'code', 'created_at', 'updated_at']

    def validate(self, data):
        for key, value in data.items():
            if isinstance(value, str) and re.search(r'<[^>]*>', value):
                raise serializers.ValidationError({key: "Input contains invalid characters or HTML tags."})
        return data