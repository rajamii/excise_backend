# licenseapplication/serializers.py

from rest_framework import serializers
from .models import LicenseApplication
from . import helpers


class LicenseApplicationSerializer(serializers.ModelSerializer):
    class Meta:
        model = LicenseApplication
        fields = '__all__'

    def validate_mobile_number(self, value):
        return helpers.validate_mobile_number(value)

    def validate_email_id(self, value):
        return helpers.validate_email_field(value)

    def validate_company_email_id(self, value):
        return helpers.validate_email_field(value)

    def validate_company_phone_number(self, value):
        return helpers.validate_mobile_number(value)

    def validate_member_mobile_number(self, value):
        return helpers.validate_mobile_number(value)

    def validate_member_email_id(self, value):
        return helpers.validate_email_field(value)

    def validate_pin_code(self, value):
        return helpers.validate_pin_code(value)

    def validate_company_pan(self, value):
        return helpers.validate_pan_number(value)

    def validate_pan(self, value):
        return helpers.validate_pan_number(value)

    def validate_company_cin(self, value):
        return helpers.validate_cin_number(value)

    def validate_latitude(self, value):
        return helpers.validate_latitude(value)

    def validate_longitude(self, value):
        return helpers.validate_longitude(value)

    def validate_gender(self, value):
        return helpers.validate_gender(value)

    def validate_status(self, value):
        return helpers.validate_status(value)

    def validate_license_type(self, value):
        return helpers.validate_license_type(value)
