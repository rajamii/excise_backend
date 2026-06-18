from rest_framework import serializers
from models.transactional.payment_gateway.models import MasterPaymentModule

class MasterPaymentModuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = MasterPaymentModule
        fields = [
            'module_code',
            'module_desc',
            'license_fee',
            'visibility_status',
            'user_id',
            'opr_date',
            'created_date',
            'modified_date'
        ]
        read_only_fields = ['created_date', 'modified_date']
