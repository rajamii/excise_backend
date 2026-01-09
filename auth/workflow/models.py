from django.db import models
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey, GenericRelation
from auth.user.models import CustomUser
from auth.roles.models import Role


class Workflow(models.Model):
    """A workflow definition (e.g., 'License Approval')."""
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)

    def __str__(self):
        return self.name

class WorkflowStage(models.Model):
    """A stage in a workflow (e.g., 'Payment Pending')."""
    workflow = models.ForeignKey(Workflow, on_delete=models.CASCADE, related_name="stages")
    name = models.CharField(max_length=255)  # Increased from 50 to 255 to match StatusMaster
    description = models.CharField(max_length=255, blank=True)
    is_initial = models.BooleanField(default=False)
    is_final = models.BooleanField(default=False)

    class Meta:
        unique_together = [("workflow", "name")]
        constraints = [
            models.UniqueConstraint(
                fields=['workflow'],
                condition=models.Q(is_initial=True),
                name='one_initial_stage_per_workflow'
            )
        ]

    def __str__(self):
        return f"{self.workflow.name}: {self.name}"

class WorkflowTransition(models.Model):
    """Allowed transitions between stages."""
    workflow = models.ForeignKey(Workflow, on_delete=models.CASCADE)
    from_stage = models.ForeignKey(WorkflowStage, on_delete=models.CASCADE, related_name="outgoing_transitions")
    to_stage = models.ForeignKey(WorkflowStage, on_delete=models.CASCADE, related_name="incoming_transitions")
    condition = models.JSONField(default=dict, blank=True)  # e.g., {"fee_paid": True}


class StagePermission(models.Model):
    """Grants roles access to specific stages (optional)."""
    stage = models.ForeignKey(WorkflowStage, on_delete=models.CASCADE)
    role = models.ForeignKey(Role, on_delete=models.CASCADE)
    can_process = models.BooleanField(default=True)

    class Meta:
        unique_together = [("stage", "role")]

# ---------- POLYMORPHIC TRANSACTION ----------
class Transaction(models.Model):
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.CharField(max_length=36)          # PK of the target object
    application = GenericForeignKey('content_type', 'object_id')

    performed_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True,
                                     related_name='workflow_performed')
    forwarded_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True,
                                     related_name='workflow_forwarded_by')
    forwarded_to = models.ForeignKey(Role, on_delete=models.SET_NULL, null=True)
    stage = models.ForeignKey(WorkflowStage, on_delete=models.PROTECT)
    remarks = models.TextField(blank=True, null=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=['content_type', 'object_id'])]
        ordering = ['-timestamp']


# ---------- POLYMORPHIC OBJECTION ----------
class Objection(models.Model):
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.CharField(max_length=36)
    application = GenericForeignKey('content_type', 'object_id')

    field_name = models.CharField(max_length=255)
    remarks = models.TextField()
    raised_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True)
    stage = models.ForeignKey(WorkflowStage, on_delete=models.SET_NULL, null=True)
    is_resolved = models.BooleanField(default=False)
    raised_on = models.DateTimeField(auto_now_add=True)
    resolved_on = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-raised_on']