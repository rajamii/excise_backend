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

    def __str__(self) -> str:
        return f"ENA Req {self.requisition_number} ({self.application_id})"


class RequisitionBulkLiterDetail(models.Model):
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
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'reqution_bulk_liter_details'
        ordering = ['-updated_at']

    def __str__(self) -> str:
        return f"{self.reference_no} ({self.licensee_id or 'NA'})"


