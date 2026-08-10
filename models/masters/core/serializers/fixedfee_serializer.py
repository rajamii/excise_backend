from rest_framework import serializers
from ..models import MasterFixedFee

class MasterFixedFeeSerializer(serializers.ModelSerializer):
    license_category_name = serializers.CharField(source='license_category.license_category', read_only=True)
    license_subcategory_name = serializers.CharField(source='license_subcategory.description', read_only=True)

    class Meta:
        model = MasterFixedFee
        fields = [
            'fee_code',
            'fee_desc',
            'amount',
            'is_active',
            'license_category',
            'license_subcategory',
            'mode',
            'fee_type',
            'license_category_name',
            'license_subcategory_name',
            'created_date',
            'modified_date',
        ]
