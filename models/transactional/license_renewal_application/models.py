from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models

from auth.user.models import CustomUser
from models.masters.core.models import LicenseCategory, LicenseSubcategory


class LicenseApplication(models.Model):
    """
    Minimal record of a successfully renewed application.

    This model intentionally keeps only the columns required by the
    license renewal module.
    """

    application_id = models.CharField(max_length=30, primary_key=True, db_index=True)
    is_approved = models.BooleanField(default=False)

    # Old license number/id in NA format (business-provided).
    old_license_id = models.CharField(max_length=60, null=True, blank=True)

    # Generic pointer to the renewed source application.
    source_content_type = models.ForeignKey(
        ContentType,
        on_delete=models.PROTECT,
        related_name="+",
        db_column="source_content_type_id",
        null=True,
        blank=True,
    )
    source_object_id = models.PositiveBigIntegerField(null=True, blank=True)
    source_object = GenericForeignKey("source_content_type", "source_object_id")

    applicant = models.ForeignKey(
        CustomUser,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="license_renewal_applications",
        db_column="applicant_id",
    )

    license_category = models.ForeignKey(
        LicenseCategory,
        on_delete=models.PROTECT,
        db_column="license_category_id",
    )
    license_sub_category = models.ForeignKey(
        LicenseSubcategory,
        on_delete=models.PROTECT,
        db_column="license_sub_category_id",
        null=True,
        blank=True,
    )

    class Meta:
        db_table = "license_renewal_application"
        indexes = [
            models.Index(fields=["applicant"]),
            models.Index(fields=["source_content_type", "source_object_id"]),
        ]
