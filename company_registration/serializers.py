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
        read_only_fields = ['id']

    def validate_emailId(self, value):
        if value:
            validate_email(value)
        return value

    def validate_pan(self, value):
        validate_pan(value)
        return value

    def name(self, value):
        validate_name(value)
        return value

    def validate_mobileNumber(self, value):
        validate_mobile_number(value)
        return value

    def validate_address(self, value):
        validate_address(value)
        return value
