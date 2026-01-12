from django.db import models

class StatusMaster(models.Model):
    status_id = models.AutoField(primary_key=True)
    status_code = models.CharField(max_length=50, unique=True)
    status_name = models.CharField(max_length=100)

    class Meta:
        db_table = 'status_master'
        verbose_name = 'Status Master'
        verbose_name_plural = 'Status Masters'
        managed = False # User said table already exists

    def __str__(self):
        return f"{self.status_name} ({self.status_code})"

class WorkflowRule(models.Model):
    current_status = models.ForeignKey(StatusMaster, on_delete=models.CASCADE, related_name='transitions_from')
    action = models.CharField(max_length=50, choices=[('APPROVE', 'Approve'), ('REJECT', 'Reject')])
    next_status = models.ForeignKey(StatusMaster, on_delete=models.CASCADE, related_name='transitions_to')
    allowed_role = models.CharField(max_length=50, help_text="Role allowed to perform this action (e.g., permit-section, commissioner)")
    
    class Meta:
        unique_together = ('current_status', 'action', 'allowed_role')
        db_table = 'workflow_rules'
        verbose_name = 'Workflow Rule'
        verbose_name_plural = 'Workflow Rules'

    def __str__(self):
        return f"{self.current_status} + {self.action} ({self.allowed_role}) -> {self.next_status}"
