from rest_framework import serializers
from .models import Purpose

class PurposeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Purpose
        fields = ['purpose_id', 'purpose_name', 'is_active', 'created_at', 'updated_at']
        read_only_fields = ['purpose_id', 'created_at', 'updated_at']
