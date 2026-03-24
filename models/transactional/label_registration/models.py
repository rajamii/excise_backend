from django.db import models
from django.utils import timezone

from auth.user.models import CustomUser


def upload_document_path(instance, filename):
    return f"label_registration/{instance.application_id}/{filename}"


class LabelRegistration(models.Model):
    application_id = models.CharField(max_length=40, primary_key=True, db_index=True)
    applicant = models.ForeignKey(
        CustomUser,
        on_delete=models.PROTECT,
        related_name='label_registrations',
    )

    status = models.CharField(max_length=30, default='Submitted')
    application_date = models.DateField(default=timezone.now)

    licensee_details = models.JSONField(default=dict, blank=True)
    product_details = models.JSONField(default=dict, blank=True)
    packaging_details = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.application_id

    class Meta:
        db_table = 'label_registration'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['applicant'], name='label_reg_applicant_idx'),
            models.Index(fields=['created_at'], name='label_reg_created_at_idx'),
        ]
