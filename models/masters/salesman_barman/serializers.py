from rest_framework import serializers
from .models import SalesmanBarmanModel
from .helpers import (
    validate_pan_number,
    validate_aadhaar_number,
    validate_phone_number,
    validate_address,
    validate_email,
)

class SalesmanBarmanSerializer(serializers.ModelSerializer):
    class Meta:
        model = SalesmanBarmanModel
        fields = '__all__'
        read_only_fields = (
            'id', 
            'applicationId', 
            'IsActive'  # New read-only field
        )
        extra_kwargs = {
            # Maintain existing behavior for file fields
            'passPhoto': {'write_only': False},
            'aadhaarCard': {'write_only': False},
            'residentialCertificate': {'write_only': False},
            'dateofBirthProof': {'write_only': False},
        }

    # Preserve all existing validation methods
    def validate_emailId(self, value):
        if value:
            validate_email(value)
        return value

    def validate_pan(self, value):  # Fixed method name to match field
        validate_pan_number(value)
        return value

    def validate_aadhaar(self, value):
        validate_aadhaar_number(value)
        return value

    def validate_mobileNumber(self, value):
        validate_phone_number(value)
        return value

    def validate_address(self, value):
        validate_address(value)
        return value
    
    # Add new validations for business logic
    def validate(self, attrs):
        # Add any additional cross-field validations here
        return attrs
    
    def validate_applicationId(self, value):
        """Ensure application ID is unique"""
        instance = getattr(self, 'instance', None)
        if instance:
            # For updates: ensure new ID doesn't conflict with others
            if SalesmanBarmanModel.objects.exclude(pk=instance.pk).filter(applicationId=value).exists():
                raise serializers.ValidationError("Application ID must be unique")
        else:
            # For creates: ensure ID doesn't already exist
            if SalesmanBarmanModel.objects.filter(applicationId=value).exists():
                raise serializers.ValidationError("Application ID must be unique")
        return value
    
    def create(self, validated_data):
        """Handle application ID generation if not provided"""
        if not validated_data.get('applicationId'):
            # Implement your custom ID generation logic here
            # Example: 
            # validated_data['applicationId'] = generate_salesman_id()
            pass
        return super().create(validated_data)
