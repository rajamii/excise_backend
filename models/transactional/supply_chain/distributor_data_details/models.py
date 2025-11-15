# yourapp/models.py
from django.db import models
from django.utils import timezone

class TransitPermitDistributorData(models.Model):
    """
    Model to store distributor data for transit permits.
    Backend uses snake_case (Python convention).
    """
    manufacturing_unit = models.CharField(max_length=255, blank=True, null=True)
    distributor_name = models.CharField(max_length=255, blank=True, null=True)
    depo_address = models.TextField(blank=True, null=True)
    

    class Meta:
        db_table = 'transit_permit_distributor_data'
        verbose_name = 'Transit Permit Distributor Data'
        verbose_name_plural = 'Transit Permit Distributor Data'

    def __str__(self):
        # defensive __str__ (avoid errors if fields are None)
        return f"{self.distributor_name or ''} - {self.manufacturing_unit or ''}"
