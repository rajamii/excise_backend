from django.db import models
from django.utils import timezone

class EnaTransitPermitDetail(models.Model):
    bill_no = models.CharField(max_length=50, default='', blank=True) # unique=True removed to allow multiple products per bill
    sole_distributor_name = models.CharField(max_length=255, default='', blank=True)
    date = models.DateField(default=timezone.now)
    depot_address = models.CharField(max_length=100, default='', blank=True)
    brand = models.CharField(max_length=255, default='', blank=True)
    size_ml = models.IntegerField(default=0)
    cases = models.IntegerField(default=0)
    vehicle_number = models.CharField(max_length=20, default='', blank=True)
    licensee_id = models.CharField(max_length=50, blank=True, null=True)
    licensee_id = models.CharField(max_length=50, blank=True, null=True)
    
    # New fields for pricing and product details
    brand_owner = models.CharField(max_length=255, default='', blank=True)
    liquor_type = models.CharField(max_length=100, default='', blank=True)
    exfactory_price_rs_per_case = models.DecimalField(max_digits=15, decimal_places=2, default=0.00, blank=True)
    excise_duty_rs_per_case = models.DecimalField(max_digits=15, decimal_places=2, default=0.00, blank=True)
    education_cess_rs_per_case = models.DecimalField(max_digits=15, decimal_places=2, default=0.00, blank=True)
    additional_excise_duty_rs_per_case = models.DecimalField(max_digits=15, decimal_places=2, default=0.00, blank=True)
    
    # New field
    manufacturing_unit_name = models.CharField(max_length=255, default='', blank=True)
    
    # Validation totals
    total_education_cess = models.DecimalField(max_digits=15, decimal_places=2, default=0.00, blank=True)
    total_excise_duty = models.DecimalField(max_digits=15, decimal_places=2, default=0.00, blank=True)
    total_additional_excise = models.DecimalField(max_digits=15, decimal_places=2, default=0.00, blank=True)
    total_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0.00, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'transit_permit_details'
        ordering = ['-created_at']

    def __str__(self):
        return f"Transit Permit {self.bill_no}"
