from django.db import models


class EnaCancellationDetail(models.Model):
    our_ref_no = models.CharField(max_length=50)
    requisition_date = models.DateTimeField()
    grain_ena_number = models.DecimalField(max_digits=18, decimal_places=2)
    bulk_spirit_type = models.CharField(max_length=255, blank=True, null=True)
    strength = models.CharField(max_length=255, blank=True, null=True)
    lifted_from = models.CharField(max_length=255)
    via_route = models.CharField(max_length=255)
    status = models.CharField(max_length=50)
    status_code = models.CharField(max_length=50, default='CN_00')
    total_bl = models.DecimalField(max_digits=18, decimal_places=2)
    requisiton_number_of_permits = models.IntegerField()
    branch_name = models.CharField(max_length=255)
    branch_address = models.CharField(max_length=500)
    branch_purpose = models.CharField(max_length=255)
    govt_officer = models.CharField(max_length=255)
    state = models.CharField(max_length=100)
    cancellation_date = models.DateTimeField()
    cancellation_br_amount = models.DecimalField(max_digits=18, decimal_places=2)
    cancelled_permit_number = models.CharField(max_length=100, blank=True, null=True)
    total_cancellation_amount = models.DecimalField(max_digits=18, decimal_places=2)
    permit_nocount = models.CharField(max_length=500, blank=True, null=True)
    licensee_id = models.CharField(max_length=50)
    cancellation_each_permit_date = models.DateTimeField(blank=True, null=True)
    refund_processed_date = models.DateTimeField(blank=True, null=True)
    refund_approved_by = models.CharField(max_length=255, blank=True, null=True)
    distillery_name = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


    class Meta:
        db_table = 'ena_cancellation_detail'
        ordering = ['-created_at']


    def __str__(self):
        return f"Cancellation {self.our_ref_no} - {self.distillery_name}"
