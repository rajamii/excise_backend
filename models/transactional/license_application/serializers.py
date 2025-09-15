from rest_framework import serializers
from .models import LicenseApplication, LicenseApplicationTransaction, LocationFee, Objection
from auth.user.models import CustomUser
from auth.roles.models import Role
from . import helpers
from .models import SiteEnquiryReport
from models.masters.core.models import District, Subdivision, PoliceStation, LicenseCategory, LicenseType
from utils.fields import CodeRelatedField
from auth.workflow.models import WorkflowStage

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

class RoleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Role
        fields = ['id', 'name']

class LicenseApplicationTransactionSerializer(serializers.ModelSerializer):
    performed_by = UserShortSerializer(read_only=True)
    forwarded_by = UserShortSerializer(read_only=True)
    forwarded_to = RoleSerializer(read_only=True)
    
    class Meta:
        model = LicenseApplicationTransaction
        fields = ['license_application', 'stage', 'remarks', 'timestamp', 'performed_by', 'forwarded_by', 'forwarded_to']

class LocationFeeSerializer(serializers.ModelSerializer):
    class Meta:
        model = LocationFee
        fields = ['location_name', 'fee_amount']

class ObjectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Objection
        fields = '__all__'

class ResolveObjectionSerializer(serializers.ModelSerializer):
    excise_district = CodeRelatedField(
        queryset=District.objects.all(), lookup_field='district_code', required=False
    )
    excise_subdivision = CodeRelatedField(
        queryset=Subdivision.objects.all(), lookup_field='subdivision_code', required=False
    )
    site_subdivision = CodeRelatedField(
        queryset=Subdivision.objects.all(), lookup_field='subdivision_code', required=False
    )
    police_station = CodeRelatedField(
        queryset=PoliceStation.objects.all(), lookup_field='police_station_code', required=False
    )
    # Add more fields if needed

    class Meta:
        model = LicenseApplication
        fields = '__all__'  # or limit to only fields needed in objection resolution

class LicenseApplicationSerializer(serializers.ModelSerializer):

    # Submit (code fields)
    excise_district = CodeRelatedField(queryset=District.objects.all(), lookup_field='district_code')
    excise_subdivision = CodeRelatedField(queryset=Subdivision.objects.all(), lookup_field='subdivision_code')
    site_subdivision = CodeRelatedField(queryset=Subdivision.objects.all(), lookup_field='subdivision_code')
    police_station = CodeRelatedField(queryset=PoliceStation.objects.all(), lookup_field='police_station_code')
    license_category = serializers.PrimaryKeyRelatedField(queryset=LicenseCategory.objects.all())
    license_type = serializers.PrimaryKeyRelatedField(queryset=LicenseType.objects.all())

    # Optional: read-only name fields
    excise_district_name = serializers.CharField(source='excise_district.district', read_only=True)
    excise_subdivision_name = serializers.CharField(source='excise_subdivision.subdivision', read_only=True)
    site_subdivision_name = serializers.CharField(source='site_subdivision.subdivision', read_only=True)
    police_station_name = serializers.CharField(source='police_station.police_station', read_only=True)
    license_category_name = serializers.CharField(source='license_category.license_category', read_only=True)
    license_type_name = serializers.CharField(source='license_type.license_type', read_only=True)

    # Read-only computed fields
    application_id = serializers.CharField(read_only=True)
    current_stage = serializers.PrimaryKeyRelatedField(read_only = True)
    workflow = serializers.PrimaryKeyRelatedField(read_only=True)
    current_stage_name = serializers.CharField(source = 'current_stage.name', read_only=True)
    is_approved = serializers.BooleanField(read_only=True)
    transactions = LicenseApplicationTransactionSerializer(many=True, read_only=True)
    latest_transaction = serializers.SerializerMethodField()

    class Meta:
        model = LicenseApplication
        fields = '__all__'
        read_only_fields = ['application_id', 'current_stage_name', 'is_approved']

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
