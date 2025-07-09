from rest_framework import serializers
from .models import LicenseApplication, LicenseApplicationTransaction, LocationFee, Objection
from auth.user.models import CustomUser
from . import helpers
from .models import SiteEnquiryReport

class SiteEnquiryReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = SiteEnquiryReport
        fields = '__all__'
        read_only_fields = ['application']

class UserShortSerializer(serializers.ModelSerializer):
    role_name = serializers.CharField(source='role.name', read_only=True)
    class Meta:
        model = CustomUser
        fields = ['id', 'username', 'role', 'role_name']

class LicenseApplicationTransactionSerializer(serializers.ModelSerializer):
    performed_by = UserShortSerializer(read_only=True)
    
    class Meta:
        model = LicenseApplicationTransaction
        fields = ['license_application', 'stage', 'remarks', 'timestamp', 'performed_by']

class LocationFeeSerializer(serializers.ModelSerializer):
    class Meta:
        model = LocationFee
        fields = ['location_name', 'fee_amount']

class ObjectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Objection
        fields = '__all__'

class LicenseApplicationSerializer(serializers.ModelSerializer):
    application_id = serializers.CharField(read_only=True)
    current_stage = serializers.CharField(read_only=True)
    is_approved = serializers.BooleanField(read_only=True)
    transactions = LicenseApplicationTransactionSerializer(many=True, read_only=True)
    latest_transaction = serializers.SerializerMethodField()

    class Meta:
        model = LicenseApplication
        fields = '__all__'
        read_only_fields = ['application_id', 'current_stage', 'is_approved']

    def get_latest_transaction(self, obj):
        transaction = obj.transactions.order_by('-timestamp').first()
        return LicenseApplicationTransactionSerializer(transaction).data if transaction else None

    def validate_license_type(self, value):
        return helpers.validate_license_type(value)

    def validate_mobile_number(self, value):
        return helpers.validate_mobile_number(value)

    def validate_email(self, value):
        return helpers.validate_email_field(value)

    def validate_company_email(self, value):
        return helpers.validate_email_field(value)

    def validate_company_phone_number(self, value):
        return helpers.validate_mobile_number(value)

    def validate_member_mobile_number(self, value):
        return helpers.validate_mobile_number(value)

    def validate_member_email(self, value):
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
