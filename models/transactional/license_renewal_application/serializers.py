from rest_framework import serializers

from .models import LicenseApplication


class LicenseApplicationSerializer(serializers.ModelSerializer):
    applicant_name = serializers.SerializerMethodField()
    current_stage_name = serializers.SerializerMethodField()
    license_category_name = serializers.SerializerMethodField()
    license_sub_category_name = serializers.SerializerMethodField()

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
        ]

    valid_up_to = serializers.SerializerMethodField()
    issued_license_id = serializers.SerializerMethodField()

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
        stage = getattr(obj, "current_stage", None)
        return getattr(stage, "name", None) if stage else None

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

