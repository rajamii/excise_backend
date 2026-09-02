from rest_framework import serializers
from .models import SecretaryBulkSpiritLog


class SecretaryBulkSpiritLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = SecretaryBulkSpiritLog
        fields = '__all__'


class SecretaryManufacturingFactorySerializer(serializers.Serializer):
    id = serializers.CharField()
    establishment_name = serializers.CharField()
    applicant_name = serializers.CharField()
    company_name = serializers.CharField(allow_blank=True, allow_null=True)
    license_number = serializers.CharField(allow_blank=True, allow_null=True)
    category = serializers.CharField()
    sub_category = serializers.CharField()  # Distillery or Brewery
    district = serializers.CharField(allow_blank=True, allow_null=True)
    business_address = serializers.CharField(allow_blank=True, allow_null=True)
    mobile_number = serializers.CharField(allow_blank=True, allow_null=True)
    email = serializers.CharField(allow_blank=True, allow_null=True)
    status = serializers.CharField()
    is_approved = serializers.BooleanField()
    
    # Bulk Spirit & Operational Metrics
    stock_bl = serializers.FloatField()
    total_requisitions_count = serializers.IntegerField()
    total_bl_requested = serializers.FloatField()
    pending_requisitions_count = serializers.IntegerField()
    approved_requisitions_count = serializers.IntegerField()
    active_transit_permits_count = serializers.IntegerField()
    dispatched_bl = serializers.FloatField()
