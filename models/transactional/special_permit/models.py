from django.contrib.contenttypes.fields import GenericRelation
from django.db import models, transaction
from django.utils.timezone import now

from auth.user.models import CustomUser
from auth.workflow.models import Objection, Transaction, Workflow, WorkflowStage
from models.masters.core.models import District, LicenseCategory, LicenseSubcategory
from models.masters.license.models import License


class SpecialPermitApplication(models.Model):
    PERMISSION_DURATION_PER_ANNUM = 'per_annum'
    PERMISSION_DURATION_PER_DAY = 'per_day'
    PERMISSION_DURATION_CHOICES = [
        (PERMISSION_DURATION_PER_ANNUM, 'Per Annum'),
        (PERMISSION_DURATION_PER_DAY, 'Per Day'),
    ]

    application_id = models.CharField(max_length=40, primary_key=True, db_index=True)
    license = models.ForeignKey(
        License,
        on_delete=models.PROTECT,
        related_name='special_permit_applications',
        db_column='license_id',
    )
    applicant = models.ForeignKey(
        CustomUser,
        on_delete=models.PROTECT,
        related_name='special_permit_applications',
        db_column='applicant_id',
    )
    excise_district = models.ForeignKey(
        District,
        on_delete=models.PROTECT,
        related_name='special_permit_applications',
        db_column='excise_district_id',
    )
    license_category = models.ForeignKey(
        LicenseCategory,
        on_delete=models.PROTECT,
        related_name='special_permit_applications',
        db_column='license_category_id',
    )
    license_sub_category = models.ForeignKey(
        LicenseSubcategory,
        on_delete=models.PROTECT,
        related_name='special_permit_applications',
        db_column='license_sub_category_id',
        null=True,
        blank=True,
    )

    financial_year = models.CharField(max_length=9)
    permission_duration = models.CharField(
        max_length=20,
        choices=PERMISSION_DURATION_CHOICES,
        default=PERMISSION_DURATION_PER_ANNUM,
    )
    permission_date = models.DateField(null=True, blank=True)

    workflow = models.ForeignKey(
        Workflow,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='special_permit_applications',
        db_column='workflow_id',
    )
    current_stage = models.ForeignKey(
        WorkflowStage,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='special_permit_applications',
        db_column='current_stage_id',
    )
    is_fee_paid = models.BooleanField(default=False)
    is_approved = models.BooleanField(default=False)
    remarks = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    selected_dates = models.JSONField(null=True, blank=True)

    transactions = GenericRelation(
        Transaction,
        content_type_field='content_type',
        object_id_field='object_id',
        related_query_name='special_permit_application',
    )
    objections = GenericRelation(
        Objection,
        content_type_field='content_type',
        object_id_field='object_id',
        related_query_name='special_permit_application',
    )

    class Meta:
        db_table = 'special_permit_application'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['license']),
            models.Index(fields=['applicant']),
            models.Index(fields=['excise_district']),
            models.Index(fields=['license_category']),
            models.Index(fields=['current_stage']),
            models.Index(fields=['financial_year']),
            models.Index(fields=['permission_duration']),
        ]

    def __str__(self):
        return self.application_id

    def clean(self):
        super().clean()
        if self.permission_duration == self.PERMISSION_DURATION_PER_DAY and not self.permission_date and not self.selected_dates:
            from django.core.exceptions import ValidationError
            raise ValidationError({'permission_date': 'Permission date or selected dates is required for per day category.'})

    @staticmethod
    def generate_fin_year(today=None) -> str:
        d = today or now().date()
        year = d.year
        if d.month >= 4:
            return f"{year}-{str(year + 1)[2:]}"
        return f"{year - 1}-{str(year)[2:]}"

    @classmethod
    def generate_application_id(cls, license_obj: License, financial_year: str | None = None) -> str:
        district_code = str(getattr(getattr(license_obj, 'excise_district', None), 'district_code', '') or '000').strip()
        fin_year = financial_year or cls.generate_fin_year()
        prefix = f"SP/{district_code}/{fin_year}"

        with transaction.atomic():
            last_app = (
                cls.objects.select_for_update()
                .filter(application_id__startswith=prefix + '/')
                .order_by('-application_id')
                .first()
            )
            last_number = 0
            if last_app and last_app.application_id:
                try:
                    last_number = int(last_app.application_id.split('/')[-1])
                except (ValueError, IndexError):
                    last_number = 0
            return f"{prefix}/{str(last_number + 1).zfill(4)}"


class MasterDryDay(models.Model):
    financial_year = models.CharField(max_length=9, unique=True)
    allowed_dates = models.JSONField(default=list)  # list of ISO strings, e.g., ["2026-08-15"]
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'master_dry_day_calendar'
        ordering = ['-financial_year']

    def __str__(self):
        return f"Dry Day Calendar {self.financial_year}"
