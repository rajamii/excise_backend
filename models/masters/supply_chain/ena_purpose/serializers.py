from rest_framework import serializers
from .models import Purpose

class PurposeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Purpose
        fields = ['id', 'purpose_name']
        read_only_fields = ['id'] 
