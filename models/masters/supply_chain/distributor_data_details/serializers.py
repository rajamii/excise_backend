# yourapp/serializers.py
from rest_framework import serializers
from .models import TransitPermitDistributorData
from models.masters.license.models import License

class TransitPermitDistributorDataSerializer(serializers.ModelSerializer):
    """
    Serializer for TransitPermitDistributorData model.
    Backend uses snake_case, DRF automatically converts to camelCase for frontend.
    """
    license_id = serializers.PrimaryKeyRelatedField(
        source='license',
        queryset=License.objects.all(),
        required=False,
        allow_null=True,
    )

    class Meta:
        model = TransitPermitDistributorData
        fields = ['id', 'license_id', 'manufacturing_unit', 'distributor_name', 'depo_address']
        read_only_fields = ['id']
