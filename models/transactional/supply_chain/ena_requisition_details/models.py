from django.db import models


class EnaRequisitionDetail(models.Model):
    requisiton_number_of_permits = models.IntegerField()
    our_ref_no = models.CharField(max_length=50)
    requisition_date = models.DateTimeField()
    lifted_from_distillery_name = models.CharField(max_length=255)
    branch_address = models.CharField(max_length=500)
    branch_purpose = models.CharField(max_length=255)
    via_route = models.CharField(max_length=255)
    govt_officer = models.CharField(max_length=255)
    grain_ena_number = models.DecimalField(max_digits=18, decimal_places=2)
    strength_from = models.DecimalField(max_digits=8, decimal_places=2)
    strength_to = models.DecimalField(max_digits=8, decimal_places=2)
    status = models.CharField(max_length=50)
    state = models.CharField(max_length=100)
    totalbl = models.DecimalField(max_digits=18, decimal_places=2)
    approval_date = models.DateTimeField()
    lifted_from = models.CharField(max_length=255)
    purpose_name = models.CharField(max_length=255)
    check_post_name = models.CharField(max_length=255)
    permit_nocount = models.CharField(max_length=500)
    br_amount = models.DecimalField(max_digits=18, decimal_places=2)
    evc_file_path = models.CharField(max_length=500)
    cancellation_br_amount = models.DecimalField(max_digits=18, decimal_places=2)
    cancellation_br_number = models.CharField(max_length=50)
    licensee_id = models.CharField(max_length=50)

    class Meta:
        db_table = 'ena_requisition_detail'
        ordering = ['-created_at']

    def __str__(self) -> str:
        return f"ENA Req {self.requisition_number} ({self.application_id})"


