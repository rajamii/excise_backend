from rest_framework import serializers

from .models import LicenseApplication


class LicenseApplicationSerializer(serializers.ModelSerializer):
    applicant_name = serializers.SerializerMethodField()
    current_stage_name = serializers.SerializerMethodField()

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
            "license_sub_category",
            "workflow",
            "current_stage",
            "current_stage_name",
            "created_at",
            "updated_at",
        ]

    def get_applicant_name(self, obj):
        user = getattr(obj, "applicant", None)
        if not user:
            return None
        full = " ".join([str(getattr(user, "first_name", "") or "").strip(), str(getattr(user, "last_name", "") or "").strip()]).strip()
        return full or getattr(user, "username", None) or getattr(user, "email", None)

    def get_current_stage_name(self, obj):
        stage = getattr(obj, "current_stage", None)
        return getattr(stage, "name", None) if stage else None
