from decimal import Decimal

from django.conf import settings
from django.db import models, transaction
from django.utils import timezone


class DistributorPermitApplication(models.Model):
    STATUS_DRAFT = 'Draft'
    STATUS_SUBMITTED = 'Submitted'
    STATUS_CHOICES = [
        (STATUS_DRAFT, 'Draft'),
        (STATUS_SUBMITTED, 'Submitted'),
    ]

    reference_no = models.CharField(max_length=50, primary_key=True, db_index=True)
    applicant = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='distributor_permit_applications',
    )
    supplier_company_name = models.CharField(max_length=255)
    logistics_partner = models.CharField(max_length=255, blank=True, default='')
    source_address = models.TextField()
    origin = models.TextField(blank=True, default='')
    destination = models.TextField(blank=True, default='')
    route_details = models.TextField(blank=True, default='')
    declaration_accepted = models.BooleanField(default=False)
    is_excise_duty_fee_paid = models.BooleanField(default=False)
    status = models.CharField(max_length=100, default=STATUS_SUBMITTED)
    officer_remarks = models.TextField(blank=True, default='')
    submitted_at = models.DateTimeField(null=True, blank=True)
    approval_date = models.DateTimeField(null=True, blank=True)
    valid_up_to = models.DateTimeField(null=True, blank=True)
    permit_wise_details = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    workflow = models.ForeignKey(
        'workflow.Workflow',
        on_delete=models.PROTECT,
        related_name='distributor_permit_applications',
        null=True,
        blank=True,
    )
    current_stage = models.ForeignKey(
        'workflow.WorkflowStage',
        on_delete=models.PROTECT,
        related_name='distributor_permit_applications',
        null=True,
        blank=True,
    )

    class Meta:
        db_table = 'distributor_permit_application'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['applicant']),
            models.Index(fields=['status']),
            models.Index(fields=['submitted_at']),
        ]

    def __str__(self):
        return self.reference_no

    @staticmethod
    def generate_financial_year(today=None) -> str:
        d = today or timezone.now().date()
        if d.month >= 4:
            return f'{d.year}-{str(d.year + 1)[2:]}'
        return f'{d.year - 1}-{str(d.year)[2:]}'

    @classmethod
    def generate_reference_no(cls, app_type='requisition', today=None) -> str:
        fin_year = cls.generate_financial_year(today)
        t = str(app_type or '').lower()
        if 'reval' in t:
            prefix_code = 'IMFLREV'
        elif 'canc' in t:
            prefix_code = 'IMFLCAN'
        else:
            prefix_code = 'IMFLREQ'

        prefix = f'{prefix_code}/{fin_year}'
        with transaction.atomic():
            last_app = (
                cls.objects.select_for_update()
                .filter(reference_no__startswith=prefix + '/')
                .order_by('-reference_no')
                .first()
            )
            last_number = 0
            if last_app and last_app.reference_no:
                try:
                    last_number = int(last_app.reference_no.split('/')[-1])
                except (ValueError, IndexError):
                    last_number = 0
            return f'{prefix}/{str(last_number + 1).zfill(4)}'


class DistributorPermitLineItem(models.Model):
    application = models.ForeignKey(
        DistributorPermitApplication,
        on_delete=models.CASCADE,
        related_name='line_items',
    )
    brand = models.ForeignKey(
        'liquor_data.MasterBrandList',
        on_delete=models.PROTECT,
        related_name='distributor_permit_line_items',
    )
    brand_name = models.CharField(max_length=255)
    size_ml = models.PositiveIntegerField()
    pieces_per_case = models.PositiveIntegerField(default=0)
    edp_per_case = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    import_pass_fee_per_case = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    mrp_per_bottle = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    additional_ed_per_case = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    education_cess_per_case = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    total_additional_ed = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    bulk_litres = models.DecimalField(max_digits=15, decimal_places=3, default=Decimal('0.000'))
    permit_number = models.CharField(max_length=100, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'distributor_permit_line_item'
        ordering = ['id']
        indexes = [
            models.Index(fields=['application']),
            models.Index(fields=['brand']),
        ]

    def __str__(self):
        return f'{self.application_id} - {self.brand_name}'


class DistributorPermitDocument(models.Model):
    application = models.ForeignKey(
        DistributorPermitApplication,
        on_delete=models.CASCADE,
        related_name='documents',
    )
    document_type = models.CharField(max_length=100)
    file = models.FileField(upload_to='distributor_permits/')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'distributor_permit_document'
        ordering = ['id']

    def __str__(self):
        return f'{self.application_id} - {self.document_type}'


class IMFLRevalidationActivationSchedule(models.Model):
    STATUS_PENDING = 'pending'
    STATUS_PROCESSED = 'processed'
    STATUS_CANCELLED = 'cancelled'

    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_PROCESSED, 'Processed'),
        (STATUS_CANCELLED, 'Cancelled'),
    ]

    distributor_permit = models.OneToOneField(
        DistributorPermitApplication,
        on_delete=models.CASCADE,
        related_name='revalidation_activation_schedule'
    )
    distributor_permit_ref_no = models.CharField(max_length=50, db_index=True)
    approval_date = models.DateTimeField()
    activation_due_at = models.DateTimeField(db_index=True)
    activated_at = models.DateTimeField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING, db_index=True)
    notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'imfl_revalidation_activation_schedule'
        ordering = ['activation_due_at', '-updated_at']

    def __str__(self) -> str:
        return f"{self.distributor_permit_ref_no} -> {self.activation_due_at}"


class IMFLRevalidation(models.Model):
    reference_no = models.CharField(max_length=50, primary_key=True, db_index=True)
    distributor_permit = models.ForeignKey(
        DistributorPermitApplication,
        on_delete=models.CASCADE,
        related_name='revalidations',
    )
    applicant = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='imfl_revalidations',
    )
    revalidation_reason = models.TextField(blank=True, default='')
    status = models.CharField(max_length=100, default='Submitted')
    officer_remarks = models.TextField(blank=True, default='')
    valid_up_to = models.DateTimeField(null=True, blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    workflow = models.ForeignKey(
        'workflow.Workflow',
        on_delete=models.PROTECT,
        related_name='imfl_revalidations',
        null=True,
        blank=True,
    )
    current_stage = models.ForeignKey(
        'workflow.WorkflowStage',
        on_delete=models.PROTECT,
        related_name='imfl_revalidations',
        null=True,
        blank=True,
    )

    class Meta:
        db_table = 'imfl_revalidation'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.reference_no} ({self.distributor_permit_id})"


class IMFLCancellation(models.Model):
    reference_no = models.CharField(max_length=50, primary_key=True, db_index=True)
    distributor_permit = models.ForeignKey(
        DistributorPermitApplication,
        on_delete=models.CASCADE,
        related_name='cancellations',
    )
    applicant = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='imfl_cancellations',
    )
    cancellation_reason = models.TextField(blank=True, default='')
    status = models.CharField(max_length=100, default='Submitted')
    officer_remarks = models.TextField(blank=True, default='')
    submitted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    workflow = models.ForeignKey(
        'workflow.Workflow',
        on_delete=models.PROTECT,
        related_name='imfl_cancellations',
        null=True,
        blank=True,
    )
    current_stage = models.ForeignKey(
        'workflow.WorkflowStage',
        on_delete=models.PROTECT,
        related_name='imfl_cancellations',
        null=True,
        blank=True,
    )

    class Meta:
        db_table = 'imfl_cancellation'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.reference_no} ({self.distributor_permit_id})"

