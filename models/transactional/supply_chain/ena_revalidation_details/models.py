from django.db import models


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
    revalidation_br_amount = models.DecimalField(max_digits=18, decimal_places=2)
    licensee_id = models.CharField(max_length=50)
    distillery_name = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'ena_revalidation_detail'
        ordering = ['-created_at']

    def __str__(self):
        return f"Revalidation {self.our_ref_no} - {self.distillery_name}"
