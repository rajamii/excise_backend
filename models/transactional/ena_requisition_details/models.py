from django.db import models


class EnaRequisitionDetail(models.Model):
    application_id = models.CharField(max_length=64, db_index=True)
    requisition_number = models.CharField(max_length=64, unique=True)
    requested_on = models.DateField()
    quantity_liters = models.DecimalField(max_digits=12, decimal_places=3)
    status = models.CharField(max_length=32, default='PENDING')
    remarks = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'ena_requisition_detail'
        ordering = ['-created_at']

    def __str__(self) -> str:
        return f"ENA Req {self.requisition_number} ({self.application_id})"


