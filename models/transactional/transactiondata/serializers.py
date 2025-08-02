from rest_framework import serializers
from .models import TransactionData
from auth.user.models import CustomUser

class TransactionDataSerializer(serializers.ModelSerializer):
    licensee = serializers.PrimaryKeyRelatedField(
        queryset=CustomUser.objects.all(),
        source='licensee_id'
    )

    class Meta:
        model = TransactionData
        fields = ['id', 'licensee_id', 'district', 'subdivision', 'license_category', 'longitude', 'latitude', 'file', 'created_at', 'updated_at', 'updated_by']