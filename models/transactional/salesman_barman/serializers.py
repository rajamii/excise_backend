from rest_framework import serializers
from auth.roles.models import Role
from .models import SalesmanBarmanModel, Transaction, Objection
from auth.workflow.serializers import WorkflowTransactionSerializer, WorkflowObjectionSerializer
from models.masters.core.models import District
from auth.user.models import CustomUser
from utils.fields import CodeRelatedField
from .helpers import validate_email, validate_pan_number, validate_aadhaar_number, validate_phone_number
from models.transactional.payment_gateway.models import PaymentSBIePayTransaction

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
     
    excise_district = CodeRelatedField(queryset=District.objects.all(), lookup_field='district_code')
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
                PaymentSBIePayTransaction.objects
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
