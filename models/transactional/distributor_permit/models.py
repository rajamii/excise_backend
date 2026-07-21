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
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default=STATUS_SUBMITTED)
    officer_remarks = models.TextField(blank=True, default='')
    submitted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

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
    def generate_reference_no(cls, today=None) -> str:
        fin_year = cls.generate_financial_year(today)
        prefix = f'DP/{fin_year}'
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
    cases = models.PositiveIntegerField()
    edp_per_case = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    import_pass_fee_per_case = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    mrp_per_bottle = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    additional_ed_per_case = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    education_cess_per_case = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    total_import = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    total_education_cess = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    total_additional_ed = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    bulk_litres = models.DecimalField(max_digits=15, decimal_places=3, default=Decimal('0.000'))
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
