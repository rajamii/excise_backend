from rest_framework import serializers

from .models import LicenseApplication


class LicenseApplicationSerializer(serializers.ModelSerializer):
    applicant_name = serializers.SerializerMethodField()
    current_stage_name = serializers.SerializerMethodField()
    license_category_name = serializers.SerializerMethodField()
    license_sub_category_name = serializers.SerializerMethodField()

    valid_up_to = serializers.SerializerMethodField()
    issued_license_id = serializers.SerializerMethodField()
    is_terminated = serializers.SerializerMethodField()
    rejection_reason = serializers.SerializerMethodField()
    status_group = serializers.SerializerMethodField()
    transactions = serializers.SerializerMethodField()

    class Meta:
        model = LicenseApplication
        fields = [
            "application_id",
            "is_approved",
            "old_license_id",
            "source_content_type",
            "source_object_id",
            "applicant",
            "applicant_name",
            "license_category",
            "license_category_name",
            "license_sub_category",
            "license_sub_category_name",
            "workflow",
            "current_stage",
            "current_stage_name",
            "created_at",
            "updated_at",
            "valid_up_to",
            "issued_license_id",
            "is_terminated",
            "rejection_reason",
            "status_group",
            "transactions",
        ]

    def get_transactions(self, obj):
        try:
            from django.contrib.contenttypes.models import ContentType
            from auth.workflow.models import Transaction as WorkflowTransaction
            from auth.workflow.serializers import WorkflowTransactionSerializer
            ct = ContentType.objects.get_for_model(obj)
            txs = WorkflowTransaction.objects.filter(
                content_type=ct,
                object_id=str(obj.pk)
            ).order_by("timestamp")
            return WorkflowTransactionSerializer(txs, many=True).data
        except Exception:
            return []

    def get_is_terminated(self, obj):
        stage = getattr(obj, "current_stage", None)
        stage_name = str(getattr(stage, "name", "") or "").lower()
        if "terminat" in stage_name or "forfeit" in stage_name or "revoke" in stage_name or "suspend" in stage_name:
            return True
        # Also check underlying License / NewLicenseApplication
        old_license = getattr(obj, "old_license_id", None)
        if old_license:
            from models.masters.license.models import License
            lic = License.objects.filter(license_id=str(old_license)).first()
            if lic and not lic.is_active:
                src_app = getattr(lic, "source_application", None)
                if src_app:
                    src_stage_name = str(getattr(getattr(src_app, "current_stage", None), "name", "") or "").lower()
                    if "terminat" in src_stage_name or "forfeit" in src_stage_name or "revoke" in src_stage_name or "suspend" in src_stage_name:
                        return True
        return False

    def get_status_group(self, obj):
        if self.get_is_terminated(obj):
            return "rejected"
        stage = getattr(obj, "current_stage", None)
        stage_name = str(getattr(stage, "name", "") or "").lower()
        if "reject" in stage_name or "terminat" in stage_name:
            return "rejected"
        if getattr(obj, "is_approved", False) or "approved" in stage_name:
            return "approved"
        if "objection" in stage_name:
            return "objection"
        if "awaiting payment" in stage_name or "payment" in stage_name:
            return "awaiting-payment"
        if stage and getattr(stage, "is_initial", False):
            return "applied"
        return "pending"

    def get_rejection_reason(self, obj):
        if self.get_is_terminated(obj):
            try:
                from django.contrib.contenttypes.models import ContentType
                from auth.workflow.models import Transaction as WorkflowTransaction
                ct = ContentType.objects.get_for_model(obj)
                term_tx = WorkflowTransaction.objects.filter(
                    content_type=ct,
                    object_id=str(obj.pk),
                    stage__name__icontains="terminat"
                ).order_by("-timestamp").first()
                if term_tx and term_tx.remarks:
                    return term_tx.remarks

                # Check underlying NLA transaction
                old_license = getattr(obj, "old_license_id", None)
                if old_license:
                    from models.masters.license.models import License
                    lic = License.objects.filter(license_id=str(old_license)).first()
                    if lic and lic.source_application:
                        src_ct = ContentType.objects.get_for_model(lic.source_application)
                        src_tx = WorkflowTransaction.objects.filter(
                            content_type=src_ct,
                            object_id=str(lic.source_application.pk),
                            stage__name__icontains="terminat"
                        ).order_by("-timestamp").first()
                        if src_tx and src_tx.remarks:
                            return src_tx.remarks
            except Exception:
                pass
            return "Application and associated license officially terminated by department administration. Security deposit deducted/forfeited."

        try:
            from django.contrib.contenttypes.models import ContentType
            from auth.workflow.models import Rejection as RejectionModel
            ct = ContentType.objects.get_for_model(obj)
            rej = RejectionModel.objects.filter(content_type=ct, object_id=str(obj.pk)).order_by("-rejected_on").first()
            if rej and rej.remarks:
                return rej.remarks
        except Exception:
            pass
        return None

    def get_valid_up_to(self, obj):
        try:
            from django.contrib.contenttypes.models import ContentType
            from models.masters.license.models import License
            ct = ContentType.objects.get_for_model(obj)
            license_obj = License.objects.filter(source_content_type=ct, source_object_id=obj.pk).first()
            if license_obj and license_obj.valid_up_to:
                return license_obj.valid_up_to.isoformat()
        except Exception:
            pass
        return None

    def get_issued_license_id(self, obj):
        try:
            from django.contrib.contenttypes.models import ContentType
            from models.masters.license.models import License
            ct = ContentType.objects.get_for_model(obj)
            license_obj = License.objects.filter(source_content_type=ct, source_object_id=obj.pk).first()
            if license_obj:
                return license_obj.license_id
        except Exception:
            pass
        return getattr(obj, "old_license_id", None)

    def get_applicant_name(self, obj):
        user = getattr(obj, "applicant", None)
        if not user:
            return None
        full = " ".join([str(getattr(user, "first_name", "") or "").strip(), str(getattr(user, "last_name", "") or "").strip()]).strip()
        return full or getattr(user, "username", None) or getattr(user, "email", None)

    def get_current_stage_name(self, obj):
        if self.get_is_terminated(obj):
            return "Terminated"
        stage = getattr(obj, "current_stage", None)
        stage_name = getattr(stage, "name", None) if stage else None
        if stage_name:
            stage_lower = str(stage_name).lower()
            if "terminat" in stage_lower or "forfeit" in stage_lower:
                return "Terminated"
        return stage_name

    def get_license_category_name(self, obj):
        cat = getattr(obj, "license_category", None)
        if not cat:
            return None
        return getattr(cat, "license_category", None) or getattr(cat, "category_name", None) or getattr(cat, "name", None) or str(cat)

    def get_license_sub_category_name(self, obj):
        sub = getattr(obj, "license_sub_category", None)
        if not sub:
            return None
        return getattr(sub, "description", None) or getattr(sub, "license_subcategory", None) or getattr(sub, "name", None) or str(sub)

