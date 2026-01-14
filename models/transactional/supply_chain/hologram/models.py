from django.db import models
from django.utils import timezone
from django.contrib.contenttypes.fields import GenericRelation
from django.conf import settings
from auth.workflow.models import Workflow, WorkflowStage, Transaction, Objection
from models.masters.supply_chain.profile.models import SupplyChainUserProfile

class HologramProcurement(models.Model):
    # Constants for status (can be used for filtering, but workflow stage is primary)
    STATUS_SUBMITTED = 'Submitted'
    STATUS_UNDER_REVIEW = 'Under IT Cell Review'
    STATUS_FORWARDED = 'Forwarded to Commissioner'
    STATUS_APPROVED = 'Approved by Commissioner'
    STATUS_REJECTED = 'Rejected by Commissioner'
    STATUS_PAYMENT_COMPLETED = 'Payment Completed'
    STATUS_CARTOON_ASSIGNED = 'Cartoon Assigned'

    ref_no = models.CharField(max_length=50, unique=True)
    licensee = models.ForeignKey(SupplyChainUserProfile, on_delete=models.CASCADE, related_name='hologram_procurements')
    manufacturing_unit = models.CharField(max_length=255) # Storing name for display
    date = models.DateTimeField(default=timezone.now)
    
    local_qty = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    export_qty = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    defence_qty = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    payment_status = models.CharField(max_length=50, blank=True, null=True)
    payment_details = models.JSONField(default=dict, blank=True)
    carton_details = models.JSONField(default=list, blank=True) # Stores assigned cartons and serials
    remarks = models.TextField(blank=True, null=True)
    
    # Workflow Integration
    workflow = models.ForeignKey(Workflow, on_delete=models.PROTECT, related_name='hologram_procurements', null=True, blank=True)
    current_stage = models.ForeignKey(WorkflowStage, on_delete=models.PROTECT, related_name='hologram_procurements', null=True, blank=True)
    
    transactions = GenericRelation(
        Transaction,
        content_type_field='content_type',
        object_id_field='object_id',
        related_query_name='hologram_procurement'
    )
    objections = GenericRelation(
        Objection,
        content_type_field='content_type',
        object_id_field='object_id',
        related_query_name='hologram_procurement'
    )

    class Meta:
        db_table = 'hologram_procurement'
        ordering = ['-date']

    def __str__(self):
        return f"{self.ref_no} - {self.licensee.manufacturing_unit_name}"


class HologramRequest(models.Model):
    STATUS_SUBMITTED = 'Submitted'
    STATUS_APPROVED = 'Approved by Permit Section'
    
    ref_no = models.CharField(max_length=50, unique=True)
    licensee = models.ForeignKey(SupplyChainUserProfile, on_delete=models.CASCADE, related_name='hologram_requests')
    submission_date = models.DateTimeField(default=timezone.now)
    usage_date = models.DateField()
    quantity = models.IntegerField()
    hologram_type = models.CharField(max_length=50, default='LOCAL') # LOCAL, EXPORT, DEFENCE
    issued_assets = models.JSONField(default=list, blank=True) # allocated rolls/serials
    rolls_assigned = models.JSONField(default=list, blank=True, help_text='Assigned rolls for daily register - cartoon_number, from_serial, to_serial, quantity')

    workflow = models.ForeignKey(Workflow, on_delete=models.PROTECT, related_name='hologram_requests', null=True, blank=True)
    current_stage = models.ForeignKey(WorkflowStage, on_delete=models.PROTECT, related_name='hologram_requests', null=True, blank=True)
    
    transactions = GenericRelation(
        Transaction,
        content_type_field='content_type',
        object_id_field='object_id',
        related_query_name='hologram_request'
    )
    objections = GenericRelation(
        Objection,
        content_type_field='content_type',
        object_id_field='object_id',
        related_query_name='hologram_request'
    )

    class Meta:
        db_table = 'hologram_request'
        ordering = ['-submission_date']

    def __str__(self):
        return f"{self.ref_no} - {self.hologram_type}"


class HologramRollsDetails(models.Model):
    STATUS_AVAILABLE = 'AVAILABLE'
    STATUS_IN_USE = 'IN_USE'
    STATUS_COMPLETED = 'COMPLETED'
    STATUS_DAMAGED = 'DAMAGED'
    
    STATUS_CHOICES = [
        (STATUS_AVAILABLE, 'Available'),
        (STATUS_IN_USE, 'In Use'),
        (STATUS_COMPLETED, 'Completed'),
        (STATUS_DAMAGED, 'Damaged'),
    ]
    
    TYPE_LOCAL = 'LOCAL'
    TYPE_EXPORT = 'EXPORT'
    TYPE_DEFENCE = 'DEFENCE'
    
    TYPE_CHOICES = [
        (TYPE_LOCAL, 'Local'),
        (TYPE_EXPORT, 'Export'),
        (TYPE_DEFENCE, 'Defence'),
    ]
    
    procurement = models.ForeignKey(HologramProcurement, on_delete=models.CASCADE, related_name='rolls_details')
    received_date = models.DateTimeField(default=timezone.now)
    carton_number = models.CharField(max_length=100, unique=True)
    type = models.CharField(max_length=50, choices=TYPE_CHOICES, blank=True, null=True)
    from_serial = models.CharField(max_length=100, blank=True, null=True)
    to_serial = models.CharField(max_length=100, blank=True, null=True)
    total_count = models.IntegerField(default=0)
    available = models.IntegerField(default=0)
    used = models.IntegerField(default=0)
    damaged = models.IntegerField(default=0)
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default=STATUS_AVAILABLE)
    
    # Tracking fields
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='created_rolls', null=True, blank=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    last_updated = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='updated_rolls', null=True, blank=True)
    
    # Usage tracking
    usage_history = models.JSONField(default=list, blank=True)
    serial_ranges = models.JSONField(default=list, blank=True)
    
    # Available range display (computed field)
    available_range = models.CharField(max_length=255, blank=True, null=True, help_text='Available serial range for this roll (e.g., "101-1000")')
    
    # Metadata
    is_new = models.BooleanField(default=True)
    new_until = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        db_table = 'hologram_rolls_details'
        ordering = ['-received_date', '-id']
        indexes = [
            models.Index(fields=['carton_number']),
            models.Index(fields=['type']),
            models.Index(fields=['status']),
            models.Index(fields=['procurement']),
        ]
    
    def __str__(self):
        return f"{self.carton_number} - {self.procurement.ref_no}"
    
    def update_status(self):
        """
        Auto-update status based on available count and assignment state
        
        Status Logic:
        - COMPLETED: No holograms left (available = 0)
        - IN_USE: Roll is assigned to a request OR has been partially used
        - AVAILABLE: Roll has holograms available and is not assigned
        """
        if self.available == 0:
            # Roll is exhausted
            self.status = self.STATUS_COMPLETED
        elif self.available < self.total_count:
            # Roll has been partially used - mark as IN_USE
            self.status = self.STATUS_IN_USE
        else:
            # Roll is fully available and not used yet
            self.status = self.STATUS_AVAILABLE
        
        self.save(update_fields=['status'])
    
    def calculate_available_range(self):
        """Calculate the available serial range based on usage_history or serial_ranges table"""
        if self.available == 0:
            return "None"
        
        # Try to get from hologram_serial_ranges table first
        available_ranges = self.ranges.filter(status='AVAILABLE').order_by('from_serial')
        if available_ranges.exists():
            # Combine consecutive ranges
            ranges_list = []
            for range_obj in available_ranges:
                ranges_list.append(f"{range_obj.from_serial}-{range_obj.to_serial}")
            return ", ".join(ranges_list)
        
        # Fallback: Calculate from usage_history
        if not self.from_serial or not self.to_serial:
            return "N/A"
        
        try:
            from_num = int(self.from_serial)
            to_num = int(self.to_serial)
            
            # Get all used ranges from usage_history
            used_ranges = []
            if self.usage_history:
                for entry in self.usage_history:
                    entry_type = entry.get('type', '').upper()
                    
                    # Handle ISSUED entries
                    if entry_type == 'ISSUED':
                        from_serial = entry.get('issuedFromSerial') or entry.get('fromSerial')
                        to_serial = entry.get('issuedToSerial') or entry.get('toSerial')
                        
                        if from_serial and to_serial:
                            try:
                                from_s = int(str(from_serial).replace(str(self.from_serial)[:-len(str(from_num))], ''))
                                to_s = int(str(to_serial).replace(str(self.from_serial)[:-len(str(from_num))], ''))
                                used_ranges.append((from_s, to_s))
                            except (ValueError, TypeError):
                                pass
                    
                    # Handle WASTAGE/DAMAGED entries
                    elif entry_type in ['WASTAGE', 'DAMAGED']:
                        from_serial = entry.get('wastageFromSerial') or entry.get('fromSerial')
                        to_serial = entry.get('wastageToSerial') or entry.get('toSerial')
                        
                        if from_serial and to_serial:
                            try:
                                from_s = int(str(from_serial).replace(str(self.from_serial)[:-len(str(from_num))], ''))
                                to_s = int(str(to_serial).replace(str(self.from_serial)[:-len(str(from_num))], ''))
                                used_ranges.append((from_s, to_s))
                            except (ValueError, TypeError):
                                pass
            
            # Sort used ranges
            used_ranges.sort()
            
            # Find available ranges
            available = []
            current = from_num
            
            for used_start, used_end in used_ranges:
                if current < used_start:
                    available.append(f"{current}-{used_start - 1}")
                current = max(current, used_end + 1)
            
            if current <= to_num:
                available.append(f"{current}-{to_num}")
            
            return ", ".join(available) if available else "None"
        except (ValueError, TypeError) as e:
            print(f"Error calculating available range for {self.carton_number}: {e}")
            return "N/A"
    
    def update_available_range(self):
        """Update the available_range field"""
        self.available_range = self.calculate_available_range()
        self.save(update_fields=['available_range'])


class DailyHologramRegister(models.Model):
    APPROVAL_STATUS_PENDING = 'PENDING'
    APPROVAL_STATUS_APPROVED = 'APPROVED'
    APPROVAL_STATUS_REJECTED = 'REJECTED'
    
    APPROVAL_STATUS_CHOICES = [
        (APPROVAL_STATUS_PENDING, 'Pending'),
        (APPROVAL_STATUS_APPROVED, 'Approved'),
        (APPROVAL_STATUS_REJECTED, 'Rejected'),
    ]
    
    # Link to Licensee
    licensee = models.ForeignKey(SupplyChainUserProfile, on_delete=models.CASCADE, related_name='daily_register_entries')
    
    # Core Data
    reference_no = models.CharField(max_length=100)
    hologram_request = models.ForeignKey(HologramRequest, on_delete=models.SET_NULL, null=True, blank=True)
    
    # Roll Info
    roll_range = models.TextField(blank=True, null=True)
    rolls_used = models.ManyToManyField(HologramRollsDetails, related_name='daily_entries', blank=True)
    
    # Cartoon tracking
    cartoon_number = models.CharField(max_length=100, blank=True)
    hologram_type = models.CharField(max_length=50, blank=True)  # LOCAL/EXPORT/DEFENCE
    
    # Dates
    submission_date = models.DateField(auto_now_add=True)
    usage_date = models.DateField()
    
    # Brand Info
    brand_details = models.CharField(max_length=255, blank=True, null=True)
    bottle_size = models.CharField(max_length=100, blank=True, null=True)
    
    # Total Allocation
    hologram_qty = models.IntegerField(default=0)
    
    # Issued Details
    issued_from = models.CharField(max_length=100, blank=True, null=True)
    issued_to = models.CharField(max_length=100, blank=True, null=True)
    issued_qty = models.IntegerField(default=0)
    issued_ranges = models.JSONField(default=list, blank=True)
    
    # Wastage Details
    wastage_from = models.CharField(max_length=100, blank=True, null=True)
    wastage_to = models.CharField(max_length=100, blank=True, null=True)
    wastage_qty = models.IntegerField(default=0)
    wastage_ranges = models.JSONField(default=list, blank=True)
    
    damage_reason = models.TextField(blank=True, null=True)
    
    # Status
    is_fixed = models.BooleanField(default=False)  # True indicates the entry is saved/locked
    
    # Approval tracking
    approval_status = models.CharField(max_length=20, choices=APPROVAL_STATUS_CHOICES, default=APPROVAL_STATUS_PENDING)
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='approved_daily_registers')
    approved_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True, null=True)
    
    # Creation tracking for chronological ordering
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    
    class Meta:
        db_table = 'daily_hologram_register'
        ordering = ['-usage_date', '-id']
        indexes = [
            models.Index(fields=['licensee', 'approval_status']),
            models.Index(fields=['cartoon_number', 'hologram_type']),
            models.Index(fields=['usage_date']),
        ]

    def __str__(self):
        return f"{self.reference_no} ({self.usage_date})"


class HologramSerialRange(models.Model):
    STATUS_AVAILABLE = 'AVAILABLE'
    STATUS_USED = 'USED'
    STATUS_DAMAGED = 'DAMAGED'
    
    STATUS_CHOICES = [
        (STATUS_AVAILABLE, 'Available'),
        (STATUS_USED, 'Used'),
        (STATUS_DAMAGED, 'Damaged'),
    ]
    
    roll = models.ForeignKey(HologramRollsDetails, on_delete=models.CASCADE, related_name='ranges')
    from_serial = models.CharField(max_length=100)
    to_serial = models.CharField(max_length=100)
    count = models.IntegerField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_AVAILABLE)
    
    # For USED status
    used_date = models.DateField(null=True, blank=True)
    reference_no = models.CharField(max_length=100, blank=True)
    brand_name = models.CharField(max_length=255, blank=True)
    bottle_size = models.CharField(max_length=100, blank=True)
    production_line = models.CharField(max_length=100, blank=True)
    
    # For DAMAGED status
    damage_date = models.DateField(null=True, blank=True)
    damage_reason = models.TextField(blank=True)
    reported_by = models.CharField(max_length=255, blank=True)
    
    # Common fields
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'hologram_serial_ranges'
        ordering = ['from_serial']
        indexes = [
            models.Index(fields=['roll', 'status']),
            models.Index(fields=['from_serial', 'to_serial']),
        ]
    
    def __str__(self):
        return f"{self.from_serial} - {self.to_serial} ({self.status})"


class HologramUsageHistory(models.Model):
    USAGE_TYPE_ISSUED = 'ISSUED'
    USAGE_TYPE_WASTAGE = 'WASTAGE'
    USAGE_TYPE_RETURNED = 'RETURNED'
    
    USAGE_TYPE_CHOICES = [
        (USAGE_TYPE_ISSUED, 'Issued for Production'),
        (USAGE_TYPE_WASTAGE, 'Wastage/Damaged'),
        (USAGE_TYPE_RETURNED, 'Returned to Stock'),
    ]
    
    roll = models.ForeignKey(HologramRollsDetails, on_delete=models.CASCADE, related_name='history')
    usage_type = models.CharField(max_length=20, choices=USAGE_TYPE_CHOICES)
    
    # Serial range affected
    from_serial = models.CharField(max_length=100)
    to_serial = models.CharField(max_length=100)
    quantity = models.IntegerField()
    
    # Reference data
    reference_no = models.CharField(max_length=100, blank=True)
    brand_name = models.CharField(max_length=255, blank=True)
    bottle_size = models.CharField(max_length=100, blank=True)
    
    # Damage specific
    damage_reason = models.TextField(blank=True)
    
    # Tracking
    date = models.DateField()
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='approved_hologram_usage')
    approved_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True)
    
    # Link to daily register
    daily_register_entry = models.ForeignKey('DailyHologramRegister', null=True, blank=True, on_delete=models.SET_NULL, related_name='usage_history')
    
    class Meta:
        db_table = 'hologram_usage_history'
        ordering = ['-date', '-approved_at']
        indexes = [
            models.Index(fields=['roll', 'usage_type']),
            models.Index(fields=['date']),
        ]
    
    def __str__(self):
        return f"{self.usage_type} - {self.from_serial} to {self.to_serial} ({self.date})"
