from rest_framework import serializers
from auth.roles.models import Role
from .models import SalesmanBarmanModel, Transaction, Objection
from auth.workflow.serializers import WorkflowTransactionSerializer, WorkflowObjectionSerializer
from models.masters.core.models import District
from auth.user.models import CustomUser
from utils.fields import CodeRelatedField
from .helpers import validate_email, validate_pan_number, validate_aadhaar_number, validate_phone_number
from models.transactional.payment_gateway.models import PaymentBilldeskTransaction

DEFAULT_NEW_LICENSE_APPLICATION_MODULE_CODE = "001"

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
    forwarded_by = RoleSerializer(read_only=True)
    forwarded_to = serializers.CharField(source='forwarded_to.name', read_only=True)
    class Meta:
        model = Transaction
        fields = ['application', 'stage', 'remarks', 'timestamp', 'performed_by', 'forwarded_by', 'forwarded_to']

class ObjectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Objection
        fields = '__all__'

class SalesmanBarmanSerializer(serializers.ModelSerializer):
    allowed_actions = serializers.SerializerMethodField()
    excise_district = CodeRelatedField(queryset=District.objects.all(), lookup_field='district_code')
    excise_district_name = serializers.CharField(source='excise_district.district', read_only=True)
    current_stage_name = serializers.CharField(source='current_stage.name', read_only=True)
    license_category_name = serializers.CharField(source='license_category.license_category', read_only=True)
    renewal_of_license_id = serializers.CharField(source='renewal_of.license_id', read_only=True)
    license_id_display = serializers.CharField(source='license.license_id', read_only=True, allow_null=True)
    new_license_application_id = serializers.CharField(source='new_license_application.application_id', read_only=True, allow_null=True)
    applicant_username = serializers.CharField(source='applicant.username', read_only=True)
    applicant_full_name = serializers.SerializerMethodField()
    transactions = WorkflowTransactionSerializer(many=True, read_only=True)
    objections = WorkflowObjectionSerializer(many=True, read_only=True)
    application_fee_payment_status = serializers.SerializerMethodField()
    application_fee_payment_status_display = serializers.SerializerMethodField()
    valid_up_to = serializers.SerializerMethodField()
    license_id = serializers.SerializerMethodField()
    renewal_application_id = serializers.SerializerMethodField()
    is_parent_license_fee_paid = serializers.SerializerMethodField()
    payment_details = serializers.SerializerMethodField()

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

    def get_allowed_actions(self, obj):
        request = self.context.get('request')
        if not request or not hasattr(request, 'user'):
            return []

        user = request.user
        role_name = getattr(getattr(user, 'role', None), 'name', '') or ''
        role_token = ''.join(ch for ch in str(role_name).lower() if ch.isalnum())

        current_stage = getattr(obj, 'current_stage', None)
        if not current_stage:
            return []

        from auth.workflow.models import WorkflowTransition
        from models.transactional.supply_chain.access_control import condition_role_matches

        transitions = WorkflowTransition.objects.filter(from_stage=current_stage)
        actions = []
        for t in transitions:
            cond = t.condition or {}
            if condition_role_matches(cond, user):
                action = cond.get('action')
                if action:
                    actions.append(str(action).strip().upper())

        if not actions:
            stage_name = str(getattr(current_stage, 'name', '') or '').lower()
            if not any(k in stage_name for k in ['approv', 'reject', 'issue', 'cancel']):
                if role_token in {'commissioner', 'jointcommissioner', 'level1', 'level2', 'level3', 'level4', 'level5', 'siteadmin'} or 'commissioner' in role_token:
                    actions = ['APPROVE', 'FORWARD', 'REJECT', 'RAISE_OBJECTION']
                else:
                    actions = ['FORWARD', 'REJECT', 'RAISE_OBJECTION']

        return list(set(actions))

    def get_valid_up_to(self, obj):
        try:
            from django.contrib.contenttypes.models import ContentType
            from models.masters.license.models import License
            ct = ContentType.objects.get_for_model(obj)
            license_obj = (
                License.objects.filter(
                    source_type="salesman_barman",
                    source_content_type=ct,
                    source_object_id=str(obj.pk),
                )
                .order_by("-issue_date", "-license_id")
                .first()
            )
            if license_obj and license_obj.valid_up_to:
                return license_obj.valid_up_to.isoformat()
        except Exception:
            pass
        return None

    def get_license_id(self, obj):
        try:
            from django.contrib.contenttypes.models import ContentType
            from models.masters.license.models import License
            ct = ContentType.objects.get_for_model(obj)
            license_obj = (
                License.objects.filter(
                    source_type="salesman_barman",
                    source_content_type=ct,
                    source_object_id=str(obj.pk),
                )
                .order_by("-issue_date", "-license_id")
                .first()
            )
            if license_obj:
                return license_obj.license_id
        except Exception:
            pass
        return None

    def get_renewal_application_id(self, obj):
        try:
            from django.contrib.contenttypes.models import ContentType
            from models.transactional.license_renewal_application.models import LicenseApplication
            
            ct = ContentType.objects.get_for_model(obj)
            renewal = LicenseApplication.objects.filter(source_content_type=ct, source_object_id=obj.pk).order_by('-created_at').first()
            if renewal:
                return renewal.application_id
        except Exception:
            pass
        return None

    def get_is_parent_license_fee_paid(self, obj):
        try:
            # 1. Check fresh license flow
            nli_app = getattr(obj, "new_license_application", None)
            if nli_app:
                return bool(nli_app.is_license_fee_paid)
            
            # 2. Check existing license / renewal flow
            main_license = getattr(obj, "license", None)
            if main_license:
                from django.utils.timezone import now
                from models.transactional.license_renewal_application.models import LicenseApplication
                
                # Check renewal applications
                renewal_apps = LicenseApplication.objects.filter(old_license_id=main_license.license_id)
                if renewal_apps.exists():
                    latest_renewal = renewal_apps.order_by("-created_at").first()
                    if latest_renewal and not latest_renewal.is_license_fee_paid:
                        return False
                
                # Check expiration
                if main_license.valid_up_to and main_license.valid_up_to < now():
                    has_paid_renewal = renewal_apps.filter(is_license_fee_paid=True).exists()
                    if not has_paid_renewal:
                        return False
        except Exception:
            pass
        return True


    def get_applicant_full_name(self, obj):
        applicant = obj.applicant
        if not applicant:
            return None
        parts = [
            str(applicant.first_name or '').strip(),
            str(applicant.middle_name or '').strip(),
            str(applicant.last_name or '').strip(),
        ]
        return ' '.join(p for p in parts if p) or applicant.username or None

    def get_latest_transaction(self, obj):
        tx = obj.transactions.order_by('-timestamp').first()
        return TransactionSerializer(tx).data if tx else None

    def _resolve_new_license_payment_status(self, obj) -> str | None:
        """
        Payment status for the linked New License application-fee payment:
        - "S" success
        - "F" failed
        - "P" pending / not yet completed
        """
        app = getattr(obj, "new_license_application", None)
        if not app:
            return None

        try:
            tx = (
                PaymentBilldeskTransaction.objects
                .only("payment_status", "transaction_date")
                .filter(
                    payer_id=str(getattr(app, "application_id", "") or "").strip(),
                    payment_module_code=DEFAULT_NEW_LICENSE_APPLICATION_MODULE_CODE,
                )
                .order_by("-transaction_date")
                .first()
            )
            status = str(getattr(tx, "payment_status", "") or "").strip().upper() if tx else ""
            if status in {"S", "F", "P"}:
                return status
        except Exception:
            pass

        return "S" if getattr(app, "is_application_fee_paid", False) else "P"

    def get_application_fee_payment_status(self, obj):
        return self._resolve_new_license_payment_status(obj)

    def get_application_fee_payment_status_display(self, obj):
        status = self._resolve_new_license_payment_status(obj)
        if status == "S":
            return "Success"
        if status == "F":
            return "Failed"
        if status == "P":
            return "Pending"
        return ""

    def get_payment_details(self, obj):
        try:
            from models.transactional.wallet.models import WalletTransaction
            tx = (
                WalletTransaction.objects.filter(
                    reference_no=obj.application_id,
                    entry_type__in=['DR', 'DEBIT', 'dr', 'debit']
                )
                .order_by('-created_at')
                .first()
            )
            if tx:
                wallet_name = 'License Fee'
                if getattr(tx, 'wallet_type', None):
                    wallet_name = getattr(tx.wallet_type, 'name', getattr(tx.wallet_type, 'code', 'License Fee'))
                return {
                    'transaction_id': tx.transaction_id,
                    'amount': float(tx.amount),
                    'wallet_type': wallet_name,
                    'head_of_account': tx.head_of_account or '0039-00-105-00-00',
                    'created_at': tx.created_at.isoformat() if tx.created_at else None,
                    'payment_method': 'Wallet (License Fee)',
                    'status': 'PAID',
                    'remarks': tx.remarks or f'Salesman/Barman registration fee paid for {obj.application_id}'
                }
        except Exception:
            pass

        if getattr(obj, 'is_print_fee_paid', False) or getattr(obj, 'is_approved', False):
            fee_amount = 3000.0
            try:
                from .views import _get_salesman_barman_registration_fee
                fee_amount = float(_get_salesman_barman_registration_fee() or 3000.0)
            except Exception:
                pass
            return {
                'transaction_id': f"TXN-{str(obj.application_id).replace('/', '')}",
                'amount': fee_amount,
                'wallet_type': 'License Fee',
                'head_of_account': '0039-00-105-00-00',
                'created_at': obj.updated_at.isoformat() if getattr(obj, 'updated_at', None) else None,
                'payment_method': 'Wallet (License Fee)',
                'status': 'PAID',
                'remarks': f'Salesman/Barman registration fee paid for {obj.application_id}'
            }
        return None

    def validate(self, attrs):
        """
        When this model is created via the standalone Salesman/Barman module,
        `new_license_application` is not set and we must enforce required fields.

        When created as part of New License flow, we allow partial data and store it
        linked to `new_license_application`.
        """
        attrs = super().validate(attrs)
        # Only enforce "required fields" on CREATE. For updates (including objection
        # resolution) we must allow partial payloads.
        if self.instance is None and not attrs.get("new_license_application"):
            required = [
                "role",
                "firstName",
                "lastName",
                "fatherHusbandName",
                "gender",
                "dob",
                "address",
                "pan",
                "aadhaar",
                "mobileNumber",
                "passPhoto",
                "aadhaarCard",
                "residentialCertificate",
                "dateofBirthProof",
                "license",
            ]
            missing = [k for k in required if not attrs.get(k)]
            if missing:
                raise serializers.ValidationError({k: "This field is required." for k in missing})
        return attrs

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
