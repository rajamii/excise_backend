# yourapp/serializers.py
from rest_framework import serializers
from .models import TransitPermitDistributorData

class TransitPermitDistributorDataSerializer(serializers.ModelSerializer):
    """
    Serializer for TransitPermitDistributorData model.
    Backend uses snake_case, DRF automatically converts to camelCase for frontend.
    """
    class Meta:
        model = TransitPermitDistributorData
        fields = ['id', 'manufacturing_unit', 'distributor_name', 'depo_address']
        read_only_fields = ['id']