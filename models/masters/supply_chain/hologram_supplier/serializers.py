from rest_framework import serializers

from .models import MasterHologramSupplier


class MasterHologramSupplierSerializer(serializers.ModelSerializer):
    class Meta:
        model = MasterHologramSupplier
        fields = [
            'id',
            'company_name',
            'post',
            'address',
            'state',
            'is_active',
        ]

