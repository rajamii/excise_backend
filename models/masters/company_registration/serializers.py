from rest_framework import serializers
from .models import CompanyModel
from .helpers import (
    validate_name,
    validate_pan,
    validate_mobile_number,
    validate_address,
    validate_email,
)

class CompanySerializer(serializers.ModelSerializer):
    class Meta:
        model = CompanyModel
        fields = '__all__'
        read_only_fields = (
            'id',
            'applicationId',
            'IsActive'
        )
        extra_kwargs = {
            'undertaking': {'write_only': True},
        }

    # Correct validation methods for each field
    def validate_companyName(self, value):
        validate_name(value)
        return value

    def validate_memberName(self, value):
        validate_name(value)
        return value

    def validate_pan(self, value):
        validate_pan(value)
        return value

    def validate_officeAddress(self, value):
        validate_address(value)
        return value

    def validate_factoryAddress(self, value):
        validate_address(value)
        return value

    def validate_memberAddress(self, value):
        validate_address(value)
        return value

    def validate_companyMobileNumber(self, value):
        validate_mobile_number(value)
        return value

    def validate_memberMobileNumber(self, value):
        validate_mobile_number(value)
        return value

    def validate_companyEmailId(self, value):
        if value:
            validate_email(value)
        return value

    def validate_memberEmailId(self, value):
        if value:
            validate_email(value)
        return value
    
    def validate_applicationId(self, value):
        """Ensure application ID is unique"""
        instance = getattr(self, 'instance', None)
        if instance:
            # For updates
            if CompanyModel.objects.exclude(pk=instance.pk).filter(applicationId=value).exists():
                raise serializers.ValidationError("Application ID must be unique")
        else:
            # For creates
            if value and CompanyModel.objects.filter(applicationId=value).exists():
                raise serializers.ValidationError("Application ID must be unique")
        return value
    
    def create(self, validated_data):
        """Auto-generate application ID if not provided"""
        if not validated_data.get('applicationId'):
            # Implement custom ID generation logic
            # Example: f"COMP-{datetime.now().strftime('%Y%m%d%H%M%S')}"
            pass
        return super().create(validated_data)
