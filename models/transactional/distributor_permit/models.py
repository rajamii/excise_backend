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
            target_model = IMFLRevalidation
        elif 'canc' in t:
            prefix_code = 'IMFLCAN'
            target_model = IMFLCancellation
        else:
            prefix_code = 'IMFLREQ'
            target_model = cls

        prefix = f'{prefix_code}/{fin_year}'
        with transaction.atomic():
            last_app = (
                target_model.objects.select_for_update()
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
        on_delete=models.SET_NULL,
        related_name='distributor_permit_line_items',
        null=True,
        blank=True,
    )
    brand_name = models.CharField(max_length=255)
    size_ml = models.PositiveIntegerField()
    pieces_per_case = models.PositiveIntegerField(default=0)
    edp_per_case = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    import_pass_fee_per_case = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    mrp_per_bottle = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    additional_ed_per_case = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    education_cess_per_case = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
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


class IMFLSupplier(models.Model):
    supplier_master_name = models.CharField(max_length=255, blank=True, default='')
    supplier_name = models.CharField(max_length=255)
    address = models.TextField(blank=True, default='')
    route_details = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'imfl_suppliers'
        ordering = ['id']

    def __str__(self):
        return f'{self.supplier_master_name or self.supplier_name}'


class IMFLBrand(models.Model):
    supplier = models.ForeignKey(
        IMFLSupplier,
        on_delete=models.CASCADE,
        related_name='brands',
        db_column='imfl_supplier_id',
        null=True,
        blank=True,
    )
    brand_name = models.CharField(max_length=255)
    size_ml = models.PositiveIntegerField(default=750)
    pieces_per_case = models.PositiveIntegerField(default=12)
    edp_per_case = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    import_pass_fee_per_case = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    mrp_per_bottle = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    additional_ed_per_case = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    education_cess_per_case = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'imfl_brands'
        ordering = ['id']

    def __str__(self):
        return f'{self.brand_name} ({self.size_ml} ml)'


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

    distributor_permit = models.ForeignKey(
        DistributorPermitApplication,
        on_delete=models.CASCADE,
        related_name='revalidation_activation_schedules'
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
    revalidated_permit_number = models.CharField(max_length=100, blank=True, default='')
    permit_wise_details = models.JSONField(default=list, blank=True)
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
    cancelled_permit_number = models.CharField(max_length=100, blank=True, default='')
    permit_wise_details = models.JSONField(default=list, blank=True)
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


class IMFLArrival(models.Model):
    distributor_permit = models.ForeignKey(
        DistributorPermitApplication,
        on_delete=models.CASCADE,
        related_name='arrivals'
    )
    permit_number = models.CharField(max_length=100, db_index=True)
    vehicle_number = models.CharField(max_length=100)
    brand_name = models.CharField(max_length=255)
    brand_type = models.CharField(max_length=100, blank=True, default='')
    supplier_name = models.CharField(max_length=255, blank=True, default='')
    size_ml = models.IntegerField(default=750)
    pieces_per_case = models.IntegerField(default=12)
    expected_cases = models.IntegerField(default=0)
    expected_bottles = models.IntegerField(default=0)
    arrived_cases = models.IntegerField(default=0)
    arrived_bottles = models.IntegerField(default=0)
    damaged_bottles = models.IntegerField(default=0)
    damaged_cases = models.IntegerField(default=0)
    good_bottles = models.IntegerField(default=0)
    good_cases = models.IntegerField(default=0)
    batch_number = models.CharField(max_length=100, blank=True, default='')
    hologram_from = models.CharField(max_length=100, blank=True, default='')
    hologram_to = models.CharField(max_length=100, blank=True, default='')
    hologram_count = models.IntegerField(default=0)
    damaged_holograms = models.TextField(blank=True, default='')
    damaged_cases_holograms = models.TextField(blank=True, default='')
    remarks = models.TextField(blank=True, default='')
    arrived_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='imfl_arrivals',
        null=True,
        blank=True
    )
    arrived_at = models.DateTimeField(default=timezone.now)
    status = models.CharField(max_length=50, default='Submitted')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'imfl_arrival'
        ordering = ['-arrived_at', '-id']

    def __str__(self):
        return f"{self.permit_number} - {self.vehicle_number} ({self.arrived_cases} cases)"


class IMFLCasesProcessed(models.Model):
    distributor_permit = models.ForeignKey(
        DistributorPermitApplication,
        on_delete=models.CASCADE,
        related_name='processed_arrivals'
    )
    permit_number = models.CharField(max_length=100, db_index=True)
    vehicle_number = models.CharField(max_length=100)
    brand_name = models.CharField(max_length=255)
    size_ml = models.IntegerField(default=750)
    expected_cases = models.IntegerField(default=0)
    arrived_cases = models.IntegerField(default=0)
    remarks = models.TextField(blank=True, default='')
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='submitted_imfl_cases_processed',
        null=True,
        blank=True
    )
    oic_officer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name='assigned_imfl_cases_processed',
        null=True,
        blank=True
    )
    status = models.CharField(
        max_length=50,
        default='under_review',
        choices=[
            ('under_review', 'Under Review'),
            ('approved', 'Approved'),
            ('rejected', 'Rejected'),
        ],
        db_index=True
    )
    officer_remarks = models.TextField(blank=True, default='')
    submitted_at = models.DateTimeField(default=timezone.now)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'imfl_cases_processed'
        ordering = ['-submitted_at', '-id']

    def __str__(self):
        return f"{self.permit_number} - {self.vehicle_number} ({self.status})"


class IMFLBrandWarehouse(models.Model):
    distributor_permit = models.ForeignKey(
        DistributorPermitApplication,
        on_delete=models.SET_NULL,
        related_name='brand_warehouse_records',
        null=True,
        blank=True
    )
    permit_number = models.CharField(max_length=100, db_index=True, blank=True, default='')
    brand_name = models.CharField(max_length=255, db_index=True)
    brand_type = models.CharField(max_length=100, blank=True, default='WHISKY')
    supplier_name = models.CharField(max_length=255, blank=True, default='')
    distributor_establishment = models.CharField(max_length=255, blank=True, default='')
    pack_size = models.IntegerField(default=750)
    pieces_per_case = models.IntegerField(default=12)
    expected_cases = models.IntegerField(default=0)
    expected_bottles = models.IntegerField(default=0)
    arrived_cases = models.IntegerField(default=0)
    arrived_bottles = models.IntegerField(default=0)
    damaged_bottles = models.IntegerField(default=0)
    damaged_cases = models.IntegerField(default=0)
    good_bottles = models.IntegerField(default=0)
    good_cases = models.IntegerField(default=0)
    current_stock = models.IntegerField(default=0)
    total_utilized = models.IntegerField(default=0)
    total_capacity = models.IntegerField(default=0)
    vehicle_number = models.CharField(max_length=100, blank=True, default='')
    batch_number = models.CharField(max_length=100, blank=True, default='')
    hologram_from = models.CharField(max_length=100, blank=True, default='')
    hologram_to = models.CharField(max_length=100, blank=True, default='')
    hologram_count = models.IntegerField(default=0)
    damaged_holograms = models.TextField(blank=True, default='')
    damaged_cases_holograms = models.TextField(blank=True, default='')
    arrival_date = models.DateTimeField(default=timezone.now)
    officer_in_charge = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name='imfl_brand_warehouse_entries',
        null=True,
        blank=True
    )
    status = models.CharField(max_length=50, default='IN_STOCK')
    remarks = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'imfl_brand_warehouse'
        ordering = ['-arrival_date', '-id']
        indexes = [
            models.Index(fields=['brand_name', 'pack_size']),
            models.Index(fields=['permit_number']),
            models.Index(fields=['arrival_date']),
        ]

    def __str__(self):
        return f"{self.brand_name} ({self.pack_size}ml) - {self.current_stock} units"


class IMFLRetailerStockDetails(models.Model):
    dispatch_reference_no = models.CharField(max_length=100, unique=True, db_index=True)
    distributor_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name='imfl_retailer_dispatches',
        null=True,
        blank=True
    )
    officer_in_charge = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name='imfl_retailer_dispatches_verified',
        null=True,
        blank=True
    )
    warehouse_record = models.ForeignKey(
        IMFLBrandWarehouse,
        on_delete=models.SET_NULL,
        related_name='retailer_dispatches',
        null=True,
        blank=True
    )
    retailer_name = models.CharField(max_length=255, db_index=True)
    retailer_license_no = models.CharField(max_length=100, blank=True, default='')
    retailer_shop_name = models.CharField(max_length=255, blank=True, default='')
    retailer_address = models.TextField(blank=True, default='')
    retailer_contact = models.CharField(max_length=50, blank=True, default='')
    brand_name = models.CharField(max_length=255, db_index=True)
    brand_type = models.CharField(max_length=100, blank=True, default='WHISKY')
    supplier_name = models.CharField(max_length=255, blank=True, default='')
    pack_size = models.IntegerField(default=750)
    pieces_per_case = models.IntegerField(default=12)
    dispatched_cases = models.IntegerField(default=0)
    dispatched_loose_bottles = models.IntegerField(default=0)
    dispatched_bottles = models.IntegerField(default=0)
    hologram_from = models.CharField(max_length=100, blank=True, default='')
    hologram_to = models.CharField(max_length=100, blank=True, default='')
    hologram_count = models.IntegerField(default=0)
    batch_number = models.CharField(max_length=100, blank=True, default='')
    vehicle_number = models.CharField(max_length=100, blank=True, default='')
    driver_name = models.CharField(max_length=100, blank=True, default='')
    driver_phone = models.CharField(max_length=50, blank=True, default='')
    challan_no = models.CharField(max_length=100, blank=True, default='')
    dispatch_date = models.DateTimeField(default=timezone.now)
    status = models.CharField(max_length=50, default='DISPATCHED')
    remarks = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'imfl_retailers_stock_details'
        ordering = ['-dispatch_date', '-id']
        indexes = [
            models.Index(fields=['dispatch_reference_no']),
            models.Index(fields=['brand_name', 'pack_size']),
            models.Index(fields=['retailer_name']),
            models.Index(fields=['dispatch_date']),
        ]

    def __str__(self):
        return f"{self.dispatch_reference_no} - {self.retailer_name}: {self.brand_name} ({self.dispatched_bottles} bottles)"
