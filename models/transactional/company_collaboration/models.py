import hashlib

from django.contrib.contenttypes.fields import GenericRelation
from django.db import models, transaction
from django.utils.timezone import now

from auth.user.models import CustomUser
from auth.workflow.models import Objection, Transaction, Workflow, WorkflowStage


def upload_document_path(instance, filename):
    return f'company_collaboration/{instance.application_id}/{filename}'


class CompanyCollaboration(models.Model):
    application_id = models.CharField(max_length=30, primary_key=True, db_index=True)
    workflow = models.ForeignKey(
        Workflow,
        on_delete=models.PROTECT,
        related_name='company_collaborations'
    )
    current_stage = models.ForeignKey(
        WorkflowStage,
        on_delete=models.PROTECT,
        related_name='company_collaborations'
    )

    is_approved = models.BooleanField(default=False)

    financial_year = models.CharField(max_length=9, default='2025-2026')
    application_year = models.CharField(max_length=9, default='2025-2026')

    brand_owner = models.CharField(max_length=120)
    brand_owner_code = models.CharField(max_length=120, blank=True, null=True)
    brand_owner_name = models.CharField(max_length=255, blank=True, null=True)
    brand_owner_address = models.TextField(blank=True, null=True)

    licensee_name = models.CharField(max_length=255)
    licensee_address = models.TextField()
    contact_person = models.CharField(max_length=255)
    contact_number = models.CharField(max_length=10)
    email_address = models.EmailField()
    license_number = models.CharField(max_length=100)
    license_type = models.CharField(max_length=100)
    establishment_type = models.CharField(max_length=100)
    business_reg_number = models.CharField(max_length=100)

    selected_brand_ids = models.JSONField(default=list, blank=True)
    selected_brands = models.JSONField(default=list, blank=True)
    fee_structure = models.JSONField(default=dict, blank=True)
    overview_summary = models.JSONField(default=dict, blank=True)
    undertaking = models.FileField(upload_to=upload_document_path)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    applicant = models.ForeignKey(
        CustomUser,
        on_delete=models.PROTECT,
        related_name='company_collaborations'
    )

    transactions = GenericRelation(
        Transaction,
        content_type_field='content_type',
        object_id_field='object_id',
        related_query_name='company_collaboration'
    )
    objections = GenericRelation(
        Objection,
        content_type_field='content_type',
        object_id_field='object_id',
        related_query_name='company_collaboration'
    )

    def save(self, *args, **kwargs):
        if not self.application_id:
            self.application_id = self.generate_application_id()
        super().save(*args, **kwargs)

    def generate_application_id(self):
        fin_year = self.generate_fin_year()
        prefix = f"CCOL/{fin_year}"

        with transaction.atomic():
            last_app = CompanyCollaboration.objects.filter(
                application_id__startswith=prefix
            ).select_for_update().order_by('-application_id').first()

            if last_app and last_app.application_id:
                try:
                    last_number = int(last_app.application_id.split('/')[-1])
                except ValueError:
                    last_number = 0
            else:
                last_number = 0

            new_number = str(last_number + 1).zfill(4)
            return f"{prefix}/{new_number}"

    @staticmethod
    def generate_fin_year():
        today = now().date()
        year = today.year
        month = today.month
        if month >= 4:
            return f"{year}-{str(year + 1)[2:]}"
        return f"{year - 1}-{str(year)[2:]}"

    @staticmethod
    def make_owner_code(brand_owner: str, manufacturing_unit_name: str = '') -> str:
        seed = f"{brand_owner}|{manufacturing_unit_name}".strip().lower()
        digest = hashlib.md5(seed.encode('utf-8')).hexdigest()[:8].upper()
        return f"BO-{digest}"

    @staticmethod
    def make_brand_code(brand_name: str, brand_owner: str = '') -> str:
        seed = f"{brand_name}|{brand_owner}".strip().lower()
        digest = hashlib.md5(seed.encode('utf-8')).hexdigest()[:8].upper()
        return f"BR-{digest}"

    class Meta:
        db_table = 'company_collaboration'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['licensee_name'], name='comp_collab_licensee_idx'),
            models.Index(fields=['contact_number'], name='comp_collab_contact_idx'),
            models.Index(fields=['application_year'], name='comp_collab_year_idx'),
            models.Index(fields=['current_stage'], name='comp_collab_stage_idx'),
            models.Index(fields=['applicant'], name='comp_collab_applicant_idx'),
        ]

