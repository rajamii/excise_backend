from django.db import models
from django.utils import timezone
from django.contrib.contenttypes.fields import GenericRelation
from auth.workflow.models import Workflow, WorkflowStage, Transaction, Objection


class EnaRequisitionDetail(models.Model):
    requisiton_number_of_permits = models.IntegerField()
    details_permits_number = models.CharField(max_length=500, blank=True, null=True)
    our_ref_no = models.CharField(max_length=50)
    requisition_date = models.DateTimeField()
    lifted_from_distillery_name = models.CharField(max_length=255)
    branch_purpose = models.CharField(max_length=255)
    via_route = models.CharField(max_length=255)
    grain_ena_number = models.DecimalField(max_digits=18, decimal_places=2)
    bulk_spirit_type = models.CharField(max_length=255, default='', blank=True)
    strength = models.CharField(max_length=255, default='', blank=True)
    status = models.CharField(max_length=50)
    rejected_by_role = models.CharField(max_length=100, blank=True, default='')
    cancellation_reason = models.TextField(blank=True, default='')
    state = models.CharField(max_length=100)
    status_code = models.CharField(max_length=50, default='RQ_00')
    totalbl = models.DecimalField(max_digits=18, decimal_places=2)
    approval_date = models.DateTimeField()
    lifted_from = models.CharField(max_length=255)
    purpose_name = models.CharField(max_length=255)
    check_post_name = models.CharField(max_length=255)
    licensee_id = models.CharField(max_length=50, blank=True, null=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    workflow = models.ForeignKey(Workflow, on_delete=models.PROTECT, related_name='ena_requisitions', null=True, blank=True)
    current_stage = models.ForeignKey(WorkflowStage, on_delete=models.PROTECT, related_name='ena_requisitions', null=True, blank=True)

    # Polymorphic links
    transactions = GenericRelation(
        Transaction,
        content_type_field='content_type',
        object_id_field='object_id',
        related_query_name='ena_requisition_detail'
    )
    objections = GenericRelation(
        Objection,
        content_type_field='content_type',
        object_id_field='object_id',
        related_query_name='ena_requisition_detail'
    )

    class Meta:
        db_table = 'ena_requisition_detail'
        ordering = ['-created_at']

    # def __str__(self) -> str:
    #     return f"ENA Req {self.requisition_number} ({self.application_id})"
def __str__(self) -> str:
    return f"ENA Req {self.our_ref_no or self.pk}"

class RequisitionBulkLiterDetail(models.Model):
    class ApprovalStatus(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        APPROVED = 'APPROVED', 'Approved'
        REJECTED = 'REJECTED', 'Rejected'

    requisition = models.OneToOneField(
        EnaRequisitionDetail,
        on_delete=models.CASCADE,
        related_name='bulk_liter_detail'
    )
    reference_no = models.CharField(max_length=50, db_index=True)
    licensee_id = models.CharField(max_length=50, blank=True, null=True, db_index=True)
    tanker_count = models.PositiveIntegerField(default=0)
    tanker_details = models.JSONField(default=list, blank=True)
    total_bulk_liter = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    approval_status = models.CharField(
        max_length=20,
        choices=ApprovalStatus.choices,
        default=ApprovalStatus.PENDING,
        db_index=True
    )
    submitted_at = models.DateTimeField(default=timezone.now)
    reviewed_at = models.DateTimeField(blank=True, null=True)
    reviewed_by = models.CharField(max_length=150, blank=True, default='')
    review_remarks = models.TextField(blank=True, default='')
    edited_by_oic = models.BooleanField(default=False, db_index=True)
    edited_at = models.DateTimeField(blank=True, null=True)
    edited_by = models.CharField(max_length=150, blank=True, default='')
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'reqution_bulk_liter_details'
        ordering = ['-updated_at']

    def __str__(self) -> str:
        return f"{self.reference_no} ({self.licensee_id or 'NA'})"


class EnaRevalidationActivationSchedule(models.Model):
    STATUS_PENDING = 'pending'
    STATUS_PROCESSED = 'processed'
    STATUS_CANCELLED = 'cancelled'

    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_PROCESSED, 'Processed'),
        (STATUS_CANCELLED, 'Cancelled'),
    ]

    requisition = models.OneToOneField(
        EnaRequisitionDetail,
        on_delete=models.CASCADE,
        related_name='revalidation_activation_schedule'
    )
    requisition_ref_no = models.CharField(max_length=50, db_index=True)
    approval_date = models.DateTimeField()
    activation_due_at = models.DateTimeField(db_index=True)
    activated_at = models.DateTimeField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING, db_index=True)
    notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'ena_revalidation_activation_schedule'
        ordering = ['activation_due_at', '-updated_at']

    def __str__(self) -> str:
        return f"{self.requisition_ref_no} -> {self.activation_due_at}"


