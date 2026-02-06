from rest_framework import serializers
from auth.roles.models import Role
from .models import SalesmanBarmanModel, Transaction, Objection
from auth.workflow.serializers import WorkflowTransactionSerializer, WorkflowObjectionSerializer
from models.masters.core.models import District
from auth.user.models import CustomUser
from utils.fields import CodeRelatedField
from .helpers import validate_email, validate_pan_number, validate_aadhaar_number, validate_phone_number

class UserShortSerializer(serializers.ModelSerializer):
    role_id = serializers.IntegerField(source='role.id', read_only=True)
    class Meta:
        model = CustomUser
        fields = ['id', 'username', 'role', 'role_id']

class RoleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Role
        fields = ['id', 'name']

class TransactionSerializer(serializers.ModelSerializer):
    performed_by = UserShortSerializer(read_only=True)
    forwarded_by = UserShortSerializer(read_only=True)
    forwarded_to = serializers.CharField(source='forwarded_to.name', read_only=True)
    class Meta:
        model = Transaction
        fields = ['application', 'stage', 'remarks', 'timestamp', 'performed_by', 'forwarded_by', 'forwarded_to']

class ObjectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Objection
        fields = '__all__'

class SalesmanBarmanSerializer(serializers.ModelSerializer):
    
    excise_district = CodeRelatedField(queryset=District.objects.all(), lookup_field='district_code')
    license_category_name = serializers.CharField(source='license_category.license_category', read_only=True)
    renewal_of_license_id = serializers.CharField(source='renewal_of.license_id', read_only=True)
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
            'IsActive',
            'created_at',
            'updated_at',
            'applicant',
            'workflow'
            ]

    def get_latest_transaction(self, obj):
        tx = obj.transactions.order_by('-timestamp').first()
        return TransactionSerializer(tx).data if tx else None

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
