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

    
    # New Field
    bottle_type = models.CharField(max_length=100, default='', blank=True)
    bottles_per_case = models.IntegerField(default=12) # Historical record of pieces per case
    
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

    # Route and Transport fields (added via migration 0004)
    to_location = models.CharField(max_length=255, default='', blank=True)
    via_route = models.CharField(max_length=255, default='', blank=True)
    checkpost_entry_name = models.CharField(max_length=255, default='', blank=True)
    checkpost_exit_name = models.CharField(max_length=255, default='', blank=True)
    driver_name = models.CharField(max_length=255, default='', blank=True)
    driver_license_no = models.CharField(max_length=255, default='', blank=True)
    transporter_name = models.CharField(max_length=255, default='', blank=True)

    # Workflow Status
    workflow = models.ForeignKey('workflow.Workflow', on_delete=models.SET_NULL, null=True, blank=True, related_name='transit_permits')
    status = models.CharField(max_length=100, default='Ready for Payment', blank=True)
    status_code = models.CharField(max_length=50, default='TRP_01', blank=True)
    current_stage = models.ForeignKey('workflow.WorkflowStage', on_delete=models.SET_NULL, null=True, blank=True, related_name='transit_permits')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'transit_permit_details'
        ordering = ['-created_at']


from django.conf import settings

class Wallet(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='wallet')
    excise_balance = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    additional_excise_balance = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    education_cess_balance = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'wallet_details'
    
    def __str__(self):
        return f"Wallet ({self.user.username})"

class WalletTransaction(models.Model):
    wallet = models.ForeignKey(Wallet, on_delete=models.CASCADE, related_name='transactions')
    transaction_type = models.CharField(max_length=50) # 'DEBIT', 'CREDIT'
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    head = models.CharField(max_length=50) # 'EXCISE', 'ADDITIONAL_EXCISE', 'EDUCATION_CESS'
    reference_no = models.CharField(max_length=100, null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'wallet_transaction_details'

    def __str__(self):
        return f"{self.transaction_type} - {self.amount} ({self.created_at})"
