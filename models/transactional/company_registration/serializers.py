from rest_framework import serializers
from .models import CompanyRegistration, Transaction, Objection
from auth.user.models import CustomUser
from auth.roles.models import Role
from auth.workflow.serializers import WorkflowTransactionSerializer, WorkflowObjectionSerializer
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


class TransactionSerializer(serializers.ModelSerializer):
    performed_by = UserShortSerializer(read_only=True)
    forwarded_by = UserShortSerializer(read_only=True)
    forwarded_to = RoleSerializer(read_only=True)
    
    class Meta:
        model = Transaction
        fields = ['company_registration', 'stage', 'remarks', 'timestamp', 'performed_by', 'forwarded_by', 'forwarded_to']


class ObjectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Objection
        fields = '__all__'


class ResolveObjectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = CompanyRegistration
        fields = '__all__'


class CompanyRegistrationSerializer(serializers.ModelSerializer):

    # Read-only computed fields
    application_id = serializers.CharField(read_only=True)
    current_stage = serializers.PrimaryKeyRelatedField(read_only=True)
    workflow = serializers.PrimaryKeyRelatedField(read_only=True)
    current_stage_name = serializers.CharField(source='current_stage.name', read_only=True)
    is_approved = serializers.BooleanField(read_only=True)
    
    transactions = WorkflowTransactionSerializer(many=True, read_only=True)
    objections = WorkflowObjectionSerializer(many=True, read_only=True)

    class Meta:
        model = CompanyRegistration
        fields = '__all__'
        read_only_fields = ['application_id', 'current_stage_name', 'is_approved', 'applicant', 'workflow']

    def get_latest_transaction(self, obj):
        transaction = obj.transactions.order_by('-timestamp').first()
        return WorkflowTransactionSerializer(transaction).data if transaction else None

    def validate_company_name(self, value):
        return helpers.validate_name(value)

    def validate_member_name(self, value):
        return helpers.validate_name(value)

    def validate_pan(self, value):
        return helpers.validate_pan_number(value)

    def validate_office_address(self, value):
        return helpers.validate_address(value)

    def validate_factory_address(self, value):
        return helpers.validate_address(value)

    def validate_member_address(self, value):
        return helpers.validate_address(value)

    def validate_company_mobile_number(self, value):
        return helpers.validate_mobile_number(value)

    def validate_member_mobile_number(self, value):
        return helpers.validate_mobile_number(value)

    def validate_company_email_id(self, value):
        if value:
            return helpers.validate_email_field(value)
        return value

    def validate_member_email_id(self, value):
        if value:
            return helpers.validate_email_field(value)
        return value

    def validate_pin_code(self, value):
        return helpers.validate_pin_code(value)
