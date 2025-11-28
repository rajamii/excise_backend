from django.db import models
from django.utils import timezone

class EnaTransitPermitDetail(models.Model):
    bill_no = models.CharField(max_length=50, unique=True, default='', blank=True)
    sole_distributor_name = models.CharField(max_length=255, default='', blank=True)
    date = models.DateField(default=timezone.now)
    depot_address = models.CharField(max_length=100, default='', blank=True)
    brand = models.CharField(max_length=255, default='', blank=True)
    size_ml = models.IntegerField(default=0)
    cases = models.IntegerField(default=0)
    vehicle_number = models.CharField(max_length=20, default='', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'transit_permit_details'
        ordering = ['-created_at']

    def __str__(self):
        return f"Transit Permit {self.bill_no}"
