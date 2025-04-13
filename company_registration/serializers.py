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
        fields = '__all__'  # Include all model fields
        read_only_fields = ['id']  # 'id' should be read-only (auto-generated primary key)

    # Custom validation for companyEmailId and memberEmailId fields
    def validate_emailId(self, value):
        if value:
            validate_email(value)  # Use custom email validator
        return value

    # Custom validation for PAN field
    def validate_pan(self, value):
        validate_pan(value)  # Use custom PAN validator
        return value

    # Custom validation for name fields (companyName, memberName)
    def name(self, value):
        validate_name(value)  # Use custom name validator
        return value

    # Custom validation for mobile number fields (company and member)
    def validate_mobileNumber(self, value):
        validate_mobile_number(value)  # Use custom mobile number validator
        return value

    # Custom validation for address fields (office, factory, member)
    def validate_address(self, value):
        validate_address(value)  # Use custom address validator
        return value
