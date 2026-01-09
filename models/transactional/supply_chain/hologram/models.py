from django.db import models
from django.utils import timezone
from django.contrib.contenttypes.fields import GenericRelation
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


class DailyHologramRegister(models.Model):
    # Link to Licensee
    licensee = models.ForeignKey(SupplyChainUserProfile, on_delete=models.CASCADE, related_name='daily_register_entries')
    
    # Core Data
    reference_no = models.CharField(max_length=100)
    hologram_request = models.ForeignKey(HologramRequest, on_delete=models.SET_NULL, null=True, blank=True)
    
    # Roll Info
    roll_range = models.TextField(blank=True, null=True)
    
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
    is_fixed = models.BooleanField(default=False) # True indicates the entry is saved/locked
    
    class Meta:
        db_table = 'daily_hologram_register'
        ordering = ['-usage_date', '-id']

    def __str__(self):
        return f"{self.reference_no} ({self.usage_date})"


class HologramRollsDetails(models.Model):
    procurement = models.ForeignKey(HologramProcurement, on_delete=models.CASCADE, related_name='rolls_details')
    received_date = models.DateTimeField(default=timezone.now)
    carton_number = models.CharField(max_length=100)
    type = models.CharField(max_length=50, blank=True, null=True)
    from_serial = models.CharField(max_length=100, blank=True, null=True)
    to_serial = models.CharField(max_length=100, blank=True, null=True)
    total_count = models.IntegerField(default=0)
    available = models.IntegerField(default=0)
    used = models.IntegerField(default=0)
    damaged = models.IntegerField(default=0)
    status = models.CharField(max_length=50, default='AVAILABLE')

    class Meta:
        db_table = 'hologram_rolls_details'
        ordering = ['carton_number']
    
    def __str__(self):
        return f"{self.carton_number} - {self.procurement.ref_no}"
