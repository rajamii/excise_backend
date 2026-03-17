from django.db import models
from django.contrib.contenttypes.fields import GenericRelation
from auth.workflow.models import Transaction, Objection, Workflow, WorkflowStage
from auth.workflow.constants import WORKFLOW_IDS
import re


class EnaRevalidationDetail(models.Model):
    our_ref_no = models.CharField(max_length=50)
    requisition_date = models.DateTimeField()
    grain_ena_number = models.DecimalField(max_digits=18, decimal_places=2)
    # Replaced strength_from/to with strength/bulk_spirit_type
    bulk_spirit_type = models.CharField(max_length=255, default='', blank=True)
    strength = models.CharField(max_length=255, default='', blank=True)
    
    lifted_from = models.CharField(max_length=255)
    via_route = models.CharField(max_length=255)
    total_bl = models.DecimalField(max_digits=18, decimal_places=2)
    br_amount = models.DecimalField(max_digits=18, decimal_places=2)
    requisiton_number_of_permits = models.IntegerField()
    branch_name = models.CharField(max_length=255)
    branch_address = models.CharField(max_length=500)
    branch_purpose = models.CharField(max_length=255)
    govt_officer = models.CharField(max_length=255)
    state = models.CharField(max_length=100)
    revalidation_date = models.DateTimeField()
    status = models.CharField(max_length=50)
    status_code = models.CharField(max_length=50, null=True, blank=True) # Added for precise status lookup
    revalidation_br_amount = models.DecimalField(max_digits=18, decimal_places=2)
    details_permits_number = models.CharField(max_length=500, blank=True, null=True)
    licensee_id = models.CharField(max_length=50)
    establishment_name = models.CharField(max_length=255, blank=True, null=True)
    distillery_name = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    workflow = models.ForeignKey(Workflow, on_delete=models.PROTECT, related_name='ena_revalidations', null=True, blank=True)
    current_stage = models.ForeignKey(WorkflowStage, on_delete=models.PROTECT, related_name='ena_revalidations', null=True, blank=True)

    # Polymorphic links
    transactions = GenericRelation(
        Transaction,
        content_type_field='content_type',
        object_id_field='object_id',
        related_query_name='ena_revalidation_detail'
    )
    objections = GenericRelation(
        Objection,
        content_type_field='content_type',
        object_id_field='object_id',
        related_query_name='ena_revalidation_detail'
    )

    class Meta:
        db_table = 'ena_revalidation_detail'
        ordering = ['-created_at']

    def __str__(self):
        return f"Revalidation {self.our_ref_no} - {self.distillery_name}"

    def _resolve_stage_backed_status(self):
        workflow_id = getattr(self, 'workflow_id', None) or WORKFLOW_IDS['ENA_REVALIDATION']
        raw_status = str(getattr(self, 'status', '') or '').strip()
        stage = None

        if self.current_stage_id:
            stage = getattr(self, 'current_stage', None)
            if stage is None:
                stage = WorkflowStage.objects.filter(id=self.current_stage_id).first()
            if stage is not None and getattr(stage, 'workflow_id', None) == workflow_id:
                return stage

        if raw_status and workflow_id == WORKFLOW_IDS['ENA_REVALIDATION']:
            status_token = re.sub(r'[^a-z0-9]+', '', raw_status.lower())

            if status_token.startswith('importpermitextends45days'):
                stage = WorkflowStage.objects.filter(
                    workflow_id=workflow_id,
                    name__istartswith='IMPORT PERMIT EXTENDS 45 DAYS'
                ).order_by('id').first()
            else:
                stage = WorkflowStage.objects.filter(
                    workflow_id=workflow_id,
                    name=raw_status
                ).first()

        return stage

    def sync_stage_backed_status(self, persist=False):
        workflow_id = getattr(self, 'workflow_id', None) or WORKFLOW_IDS['ENA_REVALIDATION']
        stage = self._resolve_stage_backed_status()
        changed_fields = []

        if stage is not None:
            if getattr(self, 'current_stage_id', None) != stage.id:
                self.current_stage = stage
                changed_fields.append('current_stage')
            if getattr(self, 'workflow_id', None) != workflow_id:
                self.workflow_id = workflow_id
                changed_fields.append('workflow')
            if str(getattr(self, 'status', '') or '') != stage.name:
                self.status = stage.name
                changed_fields.append('status')

        if persist and changed_fields and getattr(self, 'pk', None):
            update_fields = []
            if 'current_stage' in changed_fields:
                update_fields.append('current_stage')
            if 'workflow' in changed_fields:
                update_fields.append('workflow')
            if 'status' in changed_fields:
                update_fields.append('status')
            self.save(update_fields=update_fields)

        return stage, changed_fields

    def save(self, *args, **kwargs):
        self.sync_stage_backed_status(persist=False)

        super().save(*args, **kwargs)
