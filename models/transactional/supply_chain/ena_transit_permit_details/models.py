from django.db import models


class EnaTransitPermitDetail(models.Model):
    entry_date = models.DateTimeField()
    depot_address = models.CharField(max_length=500)
    serial_no = models.IntegerField()
    brand = models.CharField(max_length=255)
    quantity = models.IntegerField()
    ptn = models.IntegerField()
    nlps = models.IntegerField()
    total = models.DecimalField(max_digits=18, decimal_places=2)
    bill_number = models.CharField(max_length=50)
    status = models.CharField(max_length=50)
    sole_distributor = models.CharField(max_length=255)
    unit_name = models.CharField(max_length=255)
    total_amount = models.DecimalField(max_digits=18, decimal_places=2)
    item_count = models.IntegerField()
    licensee_id_no = models.CharField(max_length=50)
    education_cess = models.DecimalField(max_digits=18, decimal_places=2)
    excise_duty = models.DecimalField(max_digits=18, decimal_places=2)
    additional_excise_duty = models.DecimalField(max_digits=18, decimal_places=2)
    is_locked = models.BooleanField(default=False)
    payment_date = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'ena_transit_permit_detail'
        ordering = ['-created_at']

    def __str__(self):
        return f"Transit Permit {self.bill_number}"
