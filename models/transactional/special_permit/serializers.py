from rest_framework import serializers

from auth.workflow.serializers import WorkflowObjectionSerializer, WorkflowTransactionSerializer
from .models import SpecialPermitApplication, MasterDryDay


class SpecialPermitApplicationSerializer(serializers.ModelSerializer):
    application_id = serializers.CharField(read_only=True)
    current_stage = serializers.PrimaryKeyRelatedField(read_only=True)
    workflow = serializers.PrimaryKeyRelatedField(read_only=True)
    current_stage_name = serializers.CharField(source='current_stage.name', read_only=True)
    district_name = serializers.CharField(source='excise_district.district', read_only=True)
    district_code = serializers.CharField(source='excise_district.district_code', read_only=True)
    license_id = serializers.CharField(source='license.license_id', read_only=True)
    license_category_name = serializers.CharField(source='license_category.license_category', read_only=True)
    license_sub_category_name = serializers.CharField(source='license_sub_category.description', read_only=True)
    applicant_name = serializers.SerializerMethodField()
    establishment_name = serializers.SerializerMethodField()
    payment_amount = serializers.SerializerMethodField()
    dry_day_fee_type = serializers.CharField(source='license_sub_category.dry_day_fee_type', read_only=True)
    transactions = WorkflowTransactionSerializer(many=True, read_only=True)
    objections = WorkflowObjectionSerializer(many=True, read_only=True)
    establishment_address = serializers.SerializerMethodField()
    mode_of_operation = serializers.SerializerMethodField()
    payment_txn_id = serializers.SerializerMethodField()
    payment_txn_date = serializers.SerializerMethodField()
    validation_code = serializers.SerializerMethodField()
    license_title = serializers.SerializerMethodField()

    class Meta:
        model = SpecialPermitApplication
        fields = '__all__'
        read_only_fields = [
            'application_id',
            'applicant',
            'excise_district',
            'license_category',
            'license_sub_category',
            'workflow',
            'current_stage',
            'current_stage_name',
            'is_fee_paid',
            'is_approved',
        ]

    def validate(self, attrs):
        duration = attrs.get('permission_duration') or SpecialPermitApplication.PERMISSION_DURATION_PER_ANNUM
        if duration == SpecialPermitApplication.PERMISSION_DURATION_PER_DAY:
            if not attrs.get('selected_dates'):
                raise serializers.ValidationError({'selected_dates': 'Selected dates is required for per day category.'})
        return attrs

    def get_applicant_name(self, obj):
        user = getattr(obj, 'applicant', None)
        if not user:
            return None
        full_name = ' '.join([
            str(getattr(user, 'first_name', '') or '').strip(),
            str(getattr(user, 'last_name', '') or '').strip(),
        ]).strip()
        return full_name or getattr(user, 'username', None) or getattr(user, 'email', None)

    def get_establishment_name(self, obj):
        source_application = getattr(getattr(obj, 'license', None), 'source_application', None)
        if not source_application:
            return None
        for field in ('establishment_name', 'business_premises_name', 'company_name', 'applicant_name'):
            value = getattr(source_application, field, None)
            if value:
                return str(value)
        return None

    def get_payment_amount(self, obj):
        from .views import calculate_special_permit_fee
        try:
            return float(calculate_special_permit_fee(obj))
        except Exception:
            return 0.0

    def get_establishment_address(self, obj):
        source_application = getattr(getattr(obj, 'license', None), 'source_application', None)
        if not source_application:
            return None
        for field in ('business_address', 'present_address', 'permanent_address', 'company_address'):
            value = getattr(source_application, field, None)
            if value:
                return str(value)
        return None

    def get_mode_of_operation(self, obj):
        source_application = getattr(getattr(obj, 'license', None), 'source_application', None)
        if not source_application:
            return None
        return getattr(source_application, 'mode_of_operation', None)

    def _get_wallet_transaction(self, obj):
        from models.transactional.wallet.models import WalletTransaction
        if not getattr(self, '_wallet_txn_cache', None):
            self._wallet_txn_cache = {}
        if obj.application_id not in self._wallet_txn_cache:
            txn = WalletTransaction.objects.filter(reference_no=obj.application_id, entry_type='DR').first()
            self._wallet_txn_cache[obj.application_id] = txn
        return self._wallet_txn_cache[obj.application_id]

    def get_payment_txn_id(self, obj):
        txn = self._get_wallet_transaction(obj)
        return txn.transaction_id if txn else None

    def get_payment_txn_date(self, obj):
        txn = self._get_wallet_transaction(obj)
        return txn.created_at if txn else None

    def get_validation_code(self, obj):
        from django.core import signing
        return signing.dumps(
            {"applicationId": obj.application_id, "source": "special_permit"},
            salt="final-license",
        )

    def get_license_title(self, obj):
        from models.masters.core.models import LicenseTitle
        title_obj = LicenseTitle.objects.filter(name='special-permit').first()
        return title_obj.description if title_obj else 'SPECIAL PERMISSION TO OPERATE BAR ON DRY DAYS'


class MasterDryDaySerializer(serializers.ModelSerializer):
    class Meta:
        model = MasterDryDay
        fields = '__all__'

