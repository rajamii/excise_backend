from rest_framework import serializers
from ..models import MasterFixedFee

class MasterFixedFeeSerializer(serializers.ModelSerializer):
    class Meta:
        model = MasterFixedFee
        fields = ['fee_code', 'fee_desc', 'amount', 'is_active', 'created_date', 'modified_date']
