from django.db import models
from django.utils import timezone


class PaymentGatewayParameters(models.Model):
    sl_no = models.IntegerField(primary_key=True)
    payment_gateway_name = models.CharField(max_length=50)
    merchantid = models.CharField(max_length=100)
    securityid = models.CharField(max_length=100)
    encryption_key = models.CharField(max_length=255)
    return_url = models.CharField(max_length=500)
    frontend_success_url = models.CharField(max_length=500, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_date = models.DateTimeField(default=timezone.now)
    modified_date = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "sems_gateway_Parameters"

    def __str__(self) -> str:
        return f"{self.sl_no} - {self.payment_gateway_name}"


class PaymentSBIePayTransaction(models.Model):
    order_ref_number = models.CharField(max_length=50, primary_key=True)
    sbi_order_ref_number = models.CharField(max_length=50, null=True, blank=True)
    atrn = models.CharField(max_length=50, null=True, blank=True)
    
    payer_id = models.CharField(max_length=50)
    payment_module_code = models.CharField(max_length=20)
    transaction_amount = models.DecimalField(max_digits=18, decimal_places=2)
    
    head_of_account = models.CharField(max_length=200, null=True, blank=True)
    wallet_type = models.CharField(max_length=200, null=True, blank=True)
    
    transaction_url = models.CharField(max_length=2000, null=True, blank=True)
    request_payload = models.TextField(null=True, blank=True)
    response_payload = models.TextField(null=True, blank=True)
    
    payment_status = models.CharField(max_length=1, default="P") # P, S, F
    transaction_status = models.CharField(max_length=50, null=True, blank=True)
    
    pay_mode = models.CharField(max_length=50, null=True, blank=True)
    bank_ref_number = models.CharField(max_length=50, null=True, blank=True)
    bank_name = models.CharField(max_length=100, null=True, blank=True)
    
    user_id = models.CharField(max_length=50, null=True, blank=True)
    opr_date = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "sems_payment_transaction_sbiepay"

    def __str__(self):
        return f"{self.order_ref_number} ({self.payment_status})"


class PaymentSendHOA(models.Model):
    id = models.BigAutoField(primary_key=True)
    transaction_id_no = models.CharField(max_length=50)
    head_of_account = models.CharField(max_length=50)
    licensee_id = models.CharField(max_length=50, null=True, blank=True)
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    payment_module_code = models.CharField(max_length=20, null=True, blank=True)
    requisition_no = models.CharField(max_length=50, null=True, blank=True)
    opr_date = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "sems_payment_send_hoa"

#Master Tables
class MasterHeadOfAccount(models.Model):
    head_of_account = models.CharField(max_length=50, unique=True)
    sl_no = models.BigIntegerField(unique=True, blank=True, primary_key=True)
    major_head = models.CharField(max_length=10)
    sub_major_head = models.CharField(max_length=10, null=True, blank=True)
    minor_head = models.CharField(max_length=10)
    sub_head = models.CharField(max_length=10, null=True, blank=True)
    detailed_head = models.CharField(max_length=20)
    object_head = models.CharField(max_length=10, null=True, blank=True)
    detailed_head_driscription = models.CharField(max_length=500)
    pay_type = models.CharField(max_length=20, null=True, blank=True)
    visible_status = models.BooleanField(default=True)
    created_date = models.DateTimeField(default=timezone.now)
    modified_date = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "sems_master_head_of_account"

    def __str__(self):
        return self.head_of_account
    

class MasterPaymentModule(models.Model):
    module_code = models.CharField(max_length=20, primary_key=True)
    module_desc = models.CharField(max_length=200)
    license_fee = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    visibility_status = models.BooleanField(default=True)
    user_id = models.CharField(max_length=50, null=True, blank=True)
    opr_date = models.DateTimeField(null=True, blank=True)
    created_date = models.DateTimeField(default=timezone.now)
    modified_date = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "sems_master_payment_module"
       

    def __str__(self):
        return f"{self.module_code} - {self.module_desc}"
    
class PaymentModuleHoa(models.Model):
    id = models.BigAutoField(primary_key=True)
    module_code = models.ForeignKey(
        MasterPaymentModule,
        on_delete=models.RESTRICT,
        db_column="module_code",
        to_field="module_code",
    )
    wallet_type = models.ForeignKey(
        'wallet.MasterWalletType', 
        on_delete=models.RESTRICT,
        db_column="wallet_type",
        to_field="code"
    )
    head_of_account = models.ForeignKey(
        MasterHeadOfAccount,
        on_delete=models.RESTRICT,
        db_column="head_of_account",
        to_field="sl_no",
    )
    # user_id = models.CharField(max_length=50, null=True, blank=True)
    opr_date = models.DateTimeField(default=timezone.now)
    is_active = models.BooleanField(default=True)
    created_date = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "sems_module_hoa"