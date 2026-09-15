# yourapp/serializers.py
from rest_framework import serializers
from .models import TransitPermitDistributorData
from models.masters.license.models import License

class TransitPermitDistributorDataSerializer(serializers.ModelSerializer):
    """
    Serializer for TransitPermitDistributorData model.
    Supports both snake_case and camelCase for frontend and API compatibility.
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

    def to_representation(self, instance):
        data = super().to_representation(instance)
        # Populate camelCase fields for Angular frontend compatibility
        data['licenseId'] = data.get('license_id')
        data['manufacturingUnit'] = data.get('manufacturing_unit')
        data['distributorName'] = data.get('distributor_name')
        data['depoAddress'] = data.get('depo_address')
        return data

    def to_internal_value(self, data):
        normalized_data = data.copy() if hasattr(data, 'copy') else dict(data)
        if 'licenseId' in normalized_data and 'license_id' not in normalized_data:
            normalized_data['license_id'] = normalized_data['licenseId']
        if 'manufacturingUnit' in normalized_data and 'manufacturing_unit' not in normalized_data:
            normalized_data['manufacturing_unit'] = normalized_data['manufacturingUnit']
        if 'distributorName' in normalized_data and 'distributor_name' not in normalized_data:
            normalized_data['distributor_name'] = normalized_data['distributorName']
        if 'depoAddress' in normalized_data and 'depo_address' not in normalized_data:
            normalized_data['depo_address'] = normalized_data['depoAddress']
        return super().to_internal_value(normalized_data)
