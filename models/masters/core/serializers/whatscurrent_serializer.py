from rest_framework import serializers
from models.masters.core import models as master_models


class WhatsCurrentSerializer(serializers.ModelSerializer):
    # Expose is_active as both snake_case and camelCase for frontend compatibility
    isActive = serializers.BooleanField(source='is_active', required=False)

    class Meta:
        model = master_models.WhatsCurrent
        fields = ['id', 'title', 'category', 'message', 'file', 'date', 'is_active', 'isActive', 'created_at', 'updated_at']
        extra_kwargs = {
            'is_active': {'required': False},
        }
