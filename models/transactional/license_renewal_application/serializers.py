from rest_framework import serializers

from .models import LicenseApplication


class LicenseApplicationSerializer(serializers.ModelSerializer):
    class Meta:
        model = LicenseApplication
        fields = [
            "application_id",
            "is_approved",
            "old_license_id",
            "source_content_type",
            "source_object_id",
            "applicant",
            "license_category",
            "license_sub_category",
        ]
