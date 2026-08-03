from django.contrib.contenttypes.fields import GenericRelation
from django.db import models
from django.utils import timezone

from auth.user.models import CustomUser
from auth.workflow.models import Objection, Transaction, Workflow, WorkflowStage
from utils.file_validation import secure_upload_filename, validate_uploaded_file


def upload_document_path(instance, filename):
    return secure_upload_filename(filename, f"label_registration/{instance.application_id}")


class LabelRegistration(models.Model):
    application_id = models.CharField(max_length=40, primary_key=True, db_index=True)
    workflow = models.ForeignKey(
        Workflow,
        on_delete=models.PROTECT,
        related_name='label_registrations',
        null=True,
        blank=True,
    )
    current_stage = models.ForeignKey(
        WorkflowStage,
        on_delete=models.PROTECT,
        related_name='label_registrations',
        null=True,
        blank=True,
    )
    applicant = models.ForeignKey(
        CustomUser,
        on_delete=models.PROTECT,
        related_name='label_registrations',
    )

    status = models.CharField(max_length=30, default='Submitted')
    is_approved = models.BooleanField(default=False)
    application_date = models.DateField(default=timezone.now)

    licensee_details = models.JSONField(default=dict, blank=True)
    product_details = models.JSONField(default=dict, blank=True)
    packaging_details = models.JSONField(default=dict, blank=True)
    upload_details = models.JSONField(default=dict, blank=True)

    transactions = GenericRelation(
        Transaction,
        content_type_field='content_type',
        object_id_field='object_id',
        related_query_name='label_registration',
    )
    objections = GenericRelation(
        Objection,
        content_type_field='content_type',
        object_id_field='object_id',
        related_query_name='label_registration',
    )

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
            models.Index(fields=['current_stage'], name='label_reg_stage_idx'),
        ]


class LabelRegistrationDocument(models.Model):
    application = models.ForeignKey(
        LabelRegistration,
        on_delete=models.CASCADE,
        related_name='documents',
    )
    document_key = models.CharField(max_length=80)
    document_name = models.CharField(max_length=255, blank=True)
    file = models.FileField(upload_to=upload_document_path, max_length=255)
    mime_type = models.CharField(max_length=120, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'label_registration_document'
        ordering = ['document_key']
        unique_together = [('application', 'document_key')]

    def __str__(self):
        return f"{self.application_id} - {self.document_key}"

    def clean(self):
        super().clean()
        validate_uploaded_file(
            self.file,
            allowed_extensions=['pdf'],
            allowed_mime_types=['application/pdf'],
            max_size_bytes=5 * 1024 * 1024,
            field_label='Label registration document'
        )

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)
