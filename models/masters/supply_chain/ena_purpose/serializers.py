from rest_framework import serializers
from .models import Purpose

class PurposeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Purpose
        fields = ['purpose_id', 'purpose_name']
        read_only_fields = ['purpose_id'] 
