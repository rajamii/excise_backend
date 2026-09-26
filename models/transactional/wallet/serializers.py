from decimal import Decimal

from rest_framework import serializers

from .models import WalletBalance, WalletTransaction, SecurityDepositRecord


class WalletBalanceSerializer(serializers.ModelSerializer):
    class Meta:
        model = WalletBalance
        fields = "__all__"


class WalletTransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = WalletTransaction
        fields = "__all__"


class SecurityDepositRecordSerializer(serializers.ModelSerializer):
    deposit_duration_days = serializers.IntegerField(read_only=True)
    is_license_active = serializers.SerializerMethodField()
    license_status_label = serializers.SerializerMethodField()
    application_status = serializers.SerializerMethodField()
    application_stage = serializers.SerializerMethodField()
    is_application_approved = serializers.SerializerMethodField()
    license_category_name = serializers.SerializerMethodField()

    class Meta:
        model = SecurityDepositRecord
        fields = "__all__"

    def _get_application(self, obj):
        if not hasattr(obj, "_cached_app"):
            from models.transactional.new_license_application.models import NewLicenseApplication
            app = None
            if obj.application_id:
                app = NewLicenseApplication.objects.select_related("current_stage", "license_category").filter(application_id=obj.application_id).first()
            if not app and obj.user_id:
                app = NewLicenseApplication.objects.select_related("current_stage", "license_category").filter(applicant_id=obj.user_id).order_by("-created_at").first()
            obj._cached_app = app
        return obj._cached_app

    def get_is_license_active(self, obj):
        try:
            from models.masters.license.models import License
            if obj.license_id:
                lic = License.objects.filter(license_id=obj.license_id).first()
                if lic:
                    return lic.is_active
            if obj.application_id:
                lic = License.objects.filter(source_object_id=obj.application_id).first()
                if lic:
                    return lic.is_active
        except Exception:
            pass
        return None

    def get_license_status_label(self, obj):
        active = self.get_is_license_active(obj)
        if active is True:
            return "Active"
        elif active is False:
            return "Suspended / Inactive"
        return "N/A"

    def get_application_status(self, obj):
        app = self._get_application(obj)
        if not app:
            if obj.status in ("DEDUCTED", "FORFEITED"):
                return "Terminated"
            return "N/A"
        stage_name = getattr(getattr(app, "current_stage", None), "name", None)
        if stage_name and str(stage_name).strip().lower() == "terminated":
            return "Terminated"
        if obj.status in ("DEDUCTED", "FORFEITED"):
            return "Terminated"
        if getattr(app, "is_approved", False):
            return "Approved"
        try:
            if hasattr(app, "rejections") and app.rejections.exists():
                return "Rejected"
        except Exception:
            pass
        if stage_name:
            return stage_name
        return "Under Review"

    def get_application_stage(self, obj):
        app = self._get_application(obj)
        return getattr(getattr(app, "current_stage", None), "name", "N/A") if app else "N/A"

    def get_is_application_approved(self, obj):
        app = self._get_application(obj)
        return bool(getattr(app, "is_approved", False)) if app else False

    def get_license_category_name(self, obj):
        app = self._get_application(obj)
        if app and getattr(app, "license_category", None):
            return str(getattr(app.license_category, "license_category", "") or "")
        return ""


class WalletRechargeCreditSerializer(serializers.Serializer):
    transaction_id = serializers.CharField(max_length=100)
    wallet_type = serializers.CharField(max_length=30)
    head_of_account = serializers.CharField(max_length=50)
    amount = serializers.DecimalField(max_digits=18, decimal_places=2, min_value=Decimal("0.01"))
    remarks = serializers.CharField(max_length=300, required=False, allow_blank=True)


