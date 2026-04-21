from django.contrib.contenttypes.fields import GenericRelation
from django.db import models
from django.utils.timezone import now

from auth.user.models import CustomUser
from auth.workflow.models import Objection, Transaction, Workflow, WorkflowStage
from .utils import upload_document_path


class CompanyCollaboration(models.Model):
    # ── Primary key / workflow linkage ────────────────────────────────────
    application_id = models.CharField(max_length=30, primary_key=True, db_index=True)
    workflow = models.ForeignKey(
        Workflow,
        on_delete=models.PROTECT,
        related_name='company_collaborations',
    )
    current_stage = models.ForeignKey(
        WorkflowStage,
        on_delete=models.PROTECT,
        related_name='company_collaborations',
    )
    is_approved = models.BooleanField(default=False)

    # ── Year fields ───────────────────────────────────────────────────────
    # financial_year: set automatically in save() — format "2025-26"
    # application_year: sent by frontend — format "2025-26" (matches company_registration)
    financial_year = models.CharField(max_length=10, blank=True)
    application_year = models.CharField(max_length=9, default='2025-26')

    # ── Collaborating company (brand owner) — Step 2 ─────────────────────
    brand_owner = models.CharField(max_length=120)
    brand_owner_code = models.CharField(max_length=120, blank=True, null=True)
    brand_owner_name = models.CharField(max_length=255, blank=True, null=True)
    brand_owner_pan = models.CharField(max_length=20, blank=True, null=True)
    brand_owner_office_address = models.TextField(blank=True, null=True)
    brand_owner_factory_address = models.TextField(blank=True, null=True)
    brand_owner_mobile = models.CharField(max_length=15, blank=True, null=True)
    brand_owner_email = models.EmailField(blank=True, null=True)

    # ── Bottler / licensee — Step 1 ───────────────────────────────────────
    licensee_name = models.CharField(max_length=255)
    licensee_address = models.TextField()
    license_number = models.CharField(max_length=100)

    # ── Brands / fees — Step 3 ───────────────────────────────────────────
    selected_brand_ids = models.JSONField(default=list, blank=True)
    selected_brands = models.JSONField(default=list, blank=True)
    fee_structure = models.JSONField(default=dict, blank=True)
    overview_summary = models.JSONField(default=dict, blank=True)
    undertaking = models.FileField(upload_to=upload_document_path, max_length=255)

    # ── Audit ─────────────────────────────────────────────────────────────
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    applicant = models.ForeignKey(
        CustomUser,
        on_delete=models.PROTECT,
        related_name='company_collaborations',
    )

    transactions = GenericRelation(
        Transaction,
        content_type_field='content_type',
        object_id_field='object_id',
        related_query_name='company_collaboration',
    )
    objections = GenericRelation(
        Objection,
        content_type_field='content_type',
        object_id_field='object_id',
        related_query_name='company_collaboration',
    )

    # ── save() ────────────────────────────────────────────────────────────
    def save(self, *args, **kwargs):
        if not self.financial_year:
            self.financial_year = self.generate_fin_year()
        super().save(*args, **kwargs)

    # ── ID generation ─────────────────────────────────────────────────────
    @staticmethod
    def generate_fin_year() -> str:
        today = now().date()
        y, m = today.year, today.month
        if m >= 4:
            return f"{y}-{str(y + 1)[2:]}"
        return f"{y - 1}-{str(y)[2:]}"

    class Meta:
        db_table = 'company_collaboration'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['financial_year'],  name='comp_collab_year_idx'),
            models.Index(fields=['application_year'], name='comp_collab_app_year_idx'),
            models.Index(fields=['licensee_name'],   name='comp_collab_licensee_idx'),
            models.Index(fields=['current_stage'],   name='comp_collab_stage_idx'),
            models.Index(fields=['applicant'],       name='comp_collab_applicant_idx'),
        ]

    def __str__(self):
        return f"{self.application_id} — {self.licensee_name}"
