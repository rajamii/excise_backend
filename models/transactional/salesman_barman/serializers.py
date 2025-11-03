from rest_framework import serializers
from auth.roles.models import Role
from .models import SalesmanBarmanModel, SalesmanBarmanTransaction, SalesmanBarmanObjection
from auth.user.models import CustomUser
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

class TransactionSerializer(serializers.ModelSerializer):
    performed_by = UserShortSerializer(read_only=True)
    forwarded_by = UserShortSerializer(read_only=True)
    forwarded_to = serializers.CharField(source='forwarded_to.name', read_only=True)
    class Meta:
        model = SalesmanBarmanTransaction
        fields = ['application', 'stage', 'remarks', 'timestamp', 'performed_by', 'forwarded_by', 'forwarded_to']

class ObjectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = SalesmanBarmanObjection
        fields = '__all__'

class SalesmanBarmanSerializer(serializers.ModelSerializer):
    current_stage_name = serializers.CharField(source='current_stage.name', read_only=True)
    transactions = TransactionSerializer(many=True, read_only=True)
    latest_transaction = serializers.SerializerMethodField()

    class Meta:
        model = SalesmanBarmanModel
        fields = '__all__'
        read_only_fields = [
            'application_id',
            'workflow',
            'current_stage',
            'current_stage_name', 
            'is_approved', 
            'IsActive']

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