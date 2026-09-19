from django.db import models
from django.utils import timezone
from django.conf import settings
from auth.workflow.models import Workflow, WorkflowStage


class EnaBulkSpiritUsage(models.Model):
    reference_no = models.CharField(max_length=50, unique=True, db_index=True)
    licensee_id = models.CharField(max_length=50, db_index=True, blank=True, null=True)
    distillery_name = models.CharField(max_length=255, blank=True, default='')
    applicant = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='bulk_spirit_usages'
    )
    bulk_spirit_type = models.CharField(max_length=100, db_index=True)
    quantity = models.DecimalField(max_digits=18, decimal_places=2)
    purpose = models.CharField(max_length=255, blank=True, default='Production / Blending')
    remarks = models.TextField(blank=True, default='')
    status = models.CharField(max_length=50, default='Pending')
    status_code = models.CharField(max_length=50, default='BSU_00')
    rejection_reason = models.TextField(blank=True, default='')
    workflow = models.ForeignKey(
        Workflow,
        on_delete=models.PROTECT,
        related_name='bulk_spirit_usages',
        null=True,
        blank=True
    )
    current_stage = models.ForeignKey(
        WorkflowStage,
        on_delete=models.PROTECT,
        related_name='bulk_spirit_usages',
        null=True,
        blank=True
    )
    reviewed_by = models.CharField(max_length=150, blank=True, default='')
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'ena_bulk_spirit_usage'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.reference_no} ({self.bulk_spirit_type})'
