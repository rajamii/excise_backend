from django.db import models
from django.utils.timezone import now
from auth.user.models import CustomUser
from auth.workflow.models import Workflow, WorkflowStage
from .helpers import (
    validate_name,
    validate_pan,
    validate_address,
    validate_email,
    validate_mobile_number
)

def upload_document_path(instance, filename):
    return f'company_registration/{instance.companyName} {instance.applicationYear}/{filename}'

class CompanyModel(models.Model):
    # ===== Company Details =====
    brandType = models.CharField(max_length=100, db_column='brand_type')
    license = models.CharField(max_length=100, db_column='license')
    applicationYear = models.CharField(max_length=9, default='2025-2026', db_column='application_year')
    applicationId = models.CharField(
        max_length=100,
        unique=True,
        db_column='application_id',
        blank=True,
        null=True
    )
    workflow = models.ForeignKey(
        Workflow,
        on_delete=models.PROTECT,
        related_name='company_registrations',
        null=True,
        blank=True,
    )
    current_stage = models.ForeignKey(
        WorkflowStage,
        on_delete=models.PROTECT,
        related_name='company_registrations',
        null=True,
        blank=True,
    )
    applicant = models.ForeignKey(
        CustomUser,
        on_delete=models.PROTECT,
        related_name='company_registrations',
        null=True,
        blank=True,
    )
    
    companyName = models.CharField(max_length=255, validators=[validate_name], db_column='company_name')
    pan = models.CharField(max_length=10, validators=[validate_pan], db_column='pan')
    officeAddress = models.TextField(validators=[validate_address], db_column='office_address')
    country = models.CharField(max_length=100, db_column='country')
    state = models.CharField(max_length=100, db_column='state')
    factoryAddress = models.TextField(validators=[validate_address], db_column='factory_address')
    pinCode = models.PositiveIntegerField(db_column='pin_code')
    companyMobileNumber = models.BigIntegerField(
        validators=[validate_mobile_number], 
        db_column='company_mobile_number'
    )
    companyEmailId = models.EmailField(
        validators=[validate_email], 
        db_column='company_email_id', 
        blank=True
    )

    # ===== Member Details =====
    memberName = models.CharField(max_length=255, validators=[validate_name], db_column='member_name')
    memberDesignation = models.CharField(max_length=255, db_column='member_designation')
    memberMobileNumber = models.BigIntegerField(
        validators=[validate_mobile_number], 
        db_column='member_mobile_number'
    )
    memberEmailId = models.EmailField(
        validators=[validate_email], 
        db_column='member_email_id', 
        blank=True
    )
    memberAddress = models.TextField(validators=[validate_address], db_column='member_address')

    # ===== Payment Details =====
    paymentId = models.CharField(max_length=100, db_column='payment_id')
    paymentDate = models.DateField(db_column='payment_date')
    paymentAmount = models.DecimalField(max_digits=10, decimal_places=2, db_column='payment_amount')
    paymentRemarks = models.TextField(blank=True, null=True, db_column='payment_remarks')

    # ===== Document Upload =====
    undertaking = models.FileField(upload_to=upload_document_path)

    # Soft delete field
    IsActive = models.BooleanField(
        default=True,
        db_column='is_active'
    )

    class Meta:
        db_table = 'company_details'
        verbose_name = 'Company Registration'
        verbose_name_plural = 'Company Registrations'

    def __str__(self):
        return f"{self.companyName} ({self.applicationYear})"

    @property
    def application_id(self):
        # Compatibility with common workflow utilities that expect snake_case.
        return self.applicationId

    @staticmethod
    def generate_fin_year():
        today = now().date()
        year = today.year
        if today.month >= 4:
            return f"{year}-{str(year + 1)[2:]}"
        return f"{year - 1}-{str(year)[2:]}"
