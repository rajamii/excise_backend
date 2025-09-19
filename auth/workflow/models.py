from django.db import models
from ..roles.models import Role  # Weak coupling (only for StagePermission)

class Workflow(models.Model):
    """Template for a workflow (e.g., 'License Approval')."""
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)

    def __str__(self):
        return self.name

class WorkflowStage(models.Model):
    """A stage in a workflow (e.g., 'Payment Pending')."""
    workflow = models.ForeignKey(Workflow, on_delete=models.CASCADE, related_name="stages")
    name = models.CharField(max_length=50)  # e.g., "level_1_review"
    description = models.CharField(max_length=255, blank=True)
    is_initial = models.BooleanField(default=False)
    is_final = models.BooleanField(default=False)

    class Meta:
        unique_together = [("workflow", "name")]

    def __str__(self):
        return f"{self.workflow.name}: {self.name}"

class WorkflowTransition(models.Model):
    """Allowed transitions between stages."""
    workflow = models.ForeignKey(Workflow, on_delete=models.CASCADE)
    from_stage = models.ForeignKey(WorkflowStage, on_delete=models.CASCADE, related_name="outgoing_transitions")
    to_stage = models.ForeignKey(WorkflowStage, on_delete=models.CASCADE, related_name="incoming_transitions")
    condition = models.JSONField(default=dict, blank=True)  # e.g., {"fee_paid": True}

    class Meta:
        # unique_together = [("workflow", "from_stage", "to_stage")]
        pass

class StagePermission(models.Model):
    """Grants roles access to specific stages (optional)."""
    stage = models.ForeignKey(WorkflowStage, on_delete=models.CASCADE)
    role = models.ForeignKey(Role, on_delete=models.CASCADE)  # Weak link to roles
    can_process = models.BooleanField(default=True)

    class Meta:
        unique_together = [("stage", "role")]