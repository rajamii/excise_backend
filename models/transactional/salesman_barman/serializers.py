from rest_framework import serializers
from django.utils.timezone import now
from auth.roles.models import Role  # type: ignore
from .models import SalesmanBarmanModel
from auth.workflow.serializers import WorkflowTransactionSerializer, WorkflowObjectionSerializer  # type: ignore
from models.masters.core.models import District  # type: ignore
from auth.user.models import CustomUser  # type: ignore
from utils.fields import CodeRelatedField  # type: ignore
from .helpers import validate_email, validate_pan_number, validate_aadhaar_number, validate_phone_number

class UserShortSerializer(serializers.ModelSerializer):
    role_name = serializers.CharField(source='role.name', read_only=True)
    class Meta:
        model = CustomUser
        fields = ['id', 'username', 'role', 'role_name']

class RoleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Role
        fields = ['id', 'name']

class SalesmanBarmanSerializer(serializers.ModelSerializer):
    
    excise_district = CodeRelatedField(queryset=District.objects.all(), lookup_field='district_code')
    license_category_name = serializers.CharField(source='license_category.license_category', read_only=True)
    
    # READ ONLY fields for display
    license_id = serializers.CharField(source='license.license_id', read_only=True)
    establishment_name = serializers.SerializerMethodField(read_only=True)

    transactions = WorkflowTransactionSerializer(many=True, read_only=True)
    objections = WorkflowObjectionSerializer(many=True, read_only=True)

    class Meta:
        model = SalesmanBarmanModel
        fields = '__all__'
        read_only_fields = [
            'application_id',
            'workflow',
            'current_stage',
            'is_approved',
            'created_at',
            'updated_at',
            'license_id',
            'establishment_name'
        ]
    
    def get_establishment_name(self, obj):
        """Get establishment name from the linked license's source application"""
        if obj.license and obj.license.source_application:
            source = obj.license.source_application
            if hasattr(source, 'establishment_name'):
                return source.establishment_name
        return None

    # Validation
    def validate_emailId(self, value):
        if value:
            validate_email(value)
        return value

    def validate_pan(self, value):
        validate_pan_number(value)
        return value

    def validate_aadhaar(self, value):
        validate_aadhaar_number(value)
        return value

    def validate_mobileNumber(self, value):
        validate_phone_number(value)
        return value
    
    def validate_license(self, value):
        """
        Validate that the license exists and is active.
        value will be a License instance (Django handles the FK lookup).
        """
        if not value.is_active:
            raise serializers.ValidationError("The selected license is not active.")
        
        if value.valid_up_to < now().date():
            raise serializers.ValidationError("The selected license has expired.")
        
        return value