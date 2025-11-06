from rest_framework import serializers
from .models import NewLicenseApplication, Transaction, Objection
from auth.user.models import CustomUser
from auth.roles.models import Role
from models.masters.core.models import District, Subdivision, PoliceStation, LicenseCategory, LicenseSubcategory, LicenseType, Road
from utils.fields import CodeRelatedField
from . import helpers


class UserShortSerializer(serializers.ModelSerializer):
    role_name = serializers.CharField(source='role.name', read_only=True)
    
    class Meta:
        model = CustomUser
        fields = ['id', 'username', 'role', 'role_name']

class RoleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Role
        fields = ['id', 'name']

class ResolveObjectionSerializer(serializers.ModelSerializer):
    site_district = CodeRelatedField(
        queryset=District.objects.all(), lookup_field='district_code', required=False
    )
    site_subdivision = CodeRelatedField(
        queryset=Subdivision.objects.all(), lookup_field='subdivision_code', required=False
    )
    road = CodeRelatedField(
        queryset=Road.objects.all(), lookup_field='road', required=False
    )
    police_station = CodeRelatedField(
        queryset=PoliceStation.objects.all(), lookup_field='police_station_code', required=False
    )

    class Meta:
        model = NewLicenseApplication
        fields = '__all__'  # or limit to only fields needed in objection resolution

class TransactionSerializer(serializers.ModelSerializer):
    performed_by = UserShortSerializer(read_only=True)
    forwarded_by = UserShortSerializer(read_only=True)
    forwarded_to = RoleSerializer(source='forwarded_to.name', read_only=True)
    
    class Meta:
        model = Transaction
        fields = ['license_application', 'stage', 'remarks', 'timestamp', 'performed_by', 'forwarded_by', 'forwarded_to']

class ObjectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Objection
        fields = '__all__'


class NewLicenseApplicationSerializer(serializers.ModelSerializer):
    
    # Code-based lookups
    site_district = CodeRelatedField(queryset=District.objects.all(), lookup_field='district_code')
    site_subdivision = CodeRelatedField(queryset=Subdivision.objects.all(), lookup_field='subdivision_code')
    police_station = CodeRelatedField(queryset=PoliceStation.objects.all(), lookup_field='police_station_code')
    license_type = serializers.PrimaryKeyRelatedField(queryset=LicenseType.objects.all())
    license_category = serializers.PrimaryKeyRelatedField(queryset=LicenseCategory.objects.all())
    license_sub_category = serializers.PrimaryKeyRelatedField(queryset=LicenseSubcategory.objects.all())

    # Read-only display fields
    license_type_name = serializers.CharField(source='license_type.license_type', read_only=True)
    license_category_name = serializers.CharField(source='license_category.license_category', read_only=True)
    license_sub_category_name = serializers.CharField(source='license_sub_category.description', read_only=True)
    site_district_name = serializers.CharField(source='site_district.district', read_only=True)
    site_subdivision_name = serializers.CharField(source='site_subdivision.subdivision', read_only=True)
    police_station_name = serializers.CharField(source='police_station.police_station', read_only=True)

    class Meta:
        model = NewLicenseApplication
        fields = '__all__'
        read_only_fields = [
            'application_id', 'current_stage', 'is_approved', 'print_count',
            'is_print_fee_paid', 'created_at', 'updated_at'
        ]

    def validate(self, data):
        helpers.validate_mobile_number(data['mobile_number'])
        helpers.validate_email_field(data['email'])
        helpers.validate_pan_number(data['pan'])
        if data.get('company_pan'):
            helpers.validate_pan_number(data['company_pan'])
        if data.get('company_email'):
            helpers.validate_email_field(data['company_email'])
        if data.get('company_phone_number'):
            helpers.validate_mobile_number(data['company_phone_number'])
        if data.get('company_cin'):
            helpers.validate_cin_number(data['company_cin'])
        helpers.validate_pin_code(data['pin_code'])
        return data