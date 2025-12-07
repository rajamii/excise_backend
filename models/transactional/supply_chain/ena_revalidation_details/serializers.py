from rest_framework import serializers
from .models import EnaRevalidationDetail

class EnaRevalidationDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = EnaRevalidationDetail
        fields = '__all__'
