from django.db import models

class EnaTransitPermitDetail(models.Model):
    bill_no = models.CharField(max_length=50, unique=True)
    sole_distributor_name = models.CharField(max_length=255)
    date = models.DateField()
    depot_address = models.CharField(max_length=100)
    brand = models.CharField(max_length=255)
    size_ml = models.IntegerField()
    cases = models.IntegerField()
    vehicle_number = models.CharField(max_length=20)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'transit_permit_details'
        ordering = ['-created_at']

    def __str__(self):
        return f"Transit Permit {self.bill_no}"
