from django.db import models, transaction
from django.contrib.contenttypes.fields import GenericRelation
from django.utils.timezone import now
from . import helpers
from auth.user.models import CustomUser
from auth.workflow.models import Workflow, WorkflowStage, Transaction, Objection


class CompanyRegistration(models.Model):
    application_id = models.CharField(max_length=30, primary_key=True, db_index=True)
    workflow = models.ForeignKey(Workflow, on_delete=models.PROTECT, related_name='company_registrations')
    current_stage = models.ForeignKey(WorkflowStage, on_delete=models.PROTECT, related_name='company_registrations')

    is_approved = models.BooleanField(default=False)

    # ===== Company Details =====
    brand_type = models.CharField(max_length=100)
    license = models.CharField(max_length=100)
    application_year = models.CharField(max_length=9, default='2025-2026')
    
    company_name = models.CharField(max_length=255)
    pan = models.CharField(max_length=10)
    office_address = models.TextField()
    country = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    factory_address = models.TextField()
    pin_code = models.PositiveIntegerField()
    company_mobile_number = models.BigIntegerField()
    company_email_id = models.EmailField(blank=True, null=True)

    # ===== Member Details =====
    member_name = models.CharField(max_length=255)
    member_designation = models.CharField(max_length=255)
    member_mobile_number = models.BigIntegerField()
    member_email_id = models.EmailField(blank=True, null=True)
    member_address = models.TextField()

    # ===== Payment Details =====
    payment_id = models.CharField(max_length=100, blank=True, null=True)
    payment_date = models.DateField(blank=True, null=True)
    payment_amount = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    payment_remarks = models.TextField(blank=True, null=True)

    # ===== Document Upload =====
    # Using simple string path instead of function reference
    undertaking = models.FileField(upload_to='company_registration/')

    # ===== Metadata =====
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    applicant = models.ForeignKey(
        CustomUser,
        on_delete=models.PROTECT,
        related_name='company_registrations'
    )

    # Polymorphic links
    transactions = GenericRelation(
        Transaction,
        content_type_field='content_type',
        object_id_field='object_id',
        related_query_name='company_registration'
    )
    objections = GenericRelation(
        Objection,
        content_type_field='content_type',
        object_id_field='object_id',
        related_query_name='company_registration'
    )

    def clean(self):
        helpers.validate_name(self.company_name)
        helpers.validate_name(self.member_name)
        helpers.validate_pan_number(self.pan)
        helpers.validate_address(self.office_address)
        helpers.validate_address(self.factory_address)
        helpers.validate_address(self.member_address)
        helpers.validate_mobile_number(self.company_mobile_number)
        helpers.validate_mobile_number(self.member_mobile_number)
        helpers.validate_pin_code(self.pin_code)

        if self.company_email_id:
            helpers.validate_email_field(self.company_email_id)
        if self.member_email_id:
            helpers.validate_email_field(self.member_email_id)

    def save(self, *args, **kwargs):
        if not self.application_id:
            self.application_id = self.generate_application_id()
        super().save(*args, **kwargs)

    def generate_application_id(self):
        today = now().date()
        year = today.year
        month = today.month
        if month >= 4:
            fin_year = f"{year}-{str(year + 1)[2:]}"
        else:
            fin_year = f"{year - 1}-{str(year)[2:]}"

        prefix = f"COMP/{fin_year}"

        with transaction.atomic():
            last_app = CompanyRegistration.objects.filter(
                application_id__startswith=prefix
            ).order_by('-application_id').first()

            if last_app and last_app.application_id:
                last_number_str = last_app.application_id.split('/')[-1]
                try:
                    last_number = int(last_number_str)
                except ValueError:
                    last_number = 0
            else:
                last_number = 0

            new_number = last_number + 1
            new_number_str = str(new_number).zfill(4)

            return f"{prefix}/{new_number_str}"

    @staticmethod
    def generate_fin_year():
        today = now().date()
        year = today.year
        month = today.month
        if month >= 4:  # April onwards → new financial year
            return f"{year}-{str(year + 1)[2:]}"
        else:
            return f"{year - 1}-{str(year)[2:]}"

    class Meta:
        db_table = 'company_registration'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['company_name']),
            models.Index(fields=['pan']),
            models.Index(fields=['application_year']),
            models.Index(fields=['current_stage']),
            models.Index(fields=['applicant']),
        ]