from django.db import models
from django.utils import timezone


class PaymentGatewayParameter(models.Model):
    sl_no = models.IntegerField(primary_key=True)
    payment_gateway_name = models.CharField(max_length=50)
    merchantid = models.CharField(max_length=100)
    securityid = models.CharField(max_length=100)
    encryption_key = models.CharField(max_length=255)
    return_url = models.CharField(max_length=500)
    created_date = models.DateTimeField(default=timezone.now)
    modified_date = models.DateTimeField(null=True, blank=True)
    is_active = models.CharField(max_length=1, default="Y")

    class Meta:
        managed = False
        db_table = "eabgari_payment_gateway_parameters"

    def __str__(self):
        return f"{self.sl_no} - {self.payment_gateway_name}"


class PaymentBilldeskTransaction(models.Model):
    utr = models.CharField(max_length=100, primary_key=True)
    transaction_date = models.DateTimeField(default=timezone.now)
    transaction_id_no_hoa = models.CharField(max_length=50)
    payer_id = models.CharField(max_length=50)
    payment_module_code = models.CharField(max_length=20)
    transaction_amount = models.DecimalField(max_digits=18, decimal_places=2)

    request_merchantid = models.CharField(max_length=100, null=True, blank=True)
    request_currencytype = models.CharField(max_length=10, null=True, blank=True)
    request_typefield1 = models.CharField(max_length=10, null=True, blank=True)
    request_securityid = models.CharField(max_length=100, null=True, blank=True)
    request_typefield2 = models.CharField(max_length=10, null=True, blank=True)
    request_additionalinfo1 = models.CharField(max_length=200, null=True, blank=True)
    request_additionalinfo2 = models.CharField(max_length=200, null=True, blank=True)
    request_additionalinfo3 = models.CharField(max_length=200, null=True, blank=True)
    request_additionalinfo4 = models.CharField(max_length=200, null=True, blank=True)
    request_additionalinfo5 = models.CharField(max_length=200, null=True, blank=True)
    request_additionalinfo6 = models.CharField(max_length=200, null=True, blank=True)
    request_additionalinfo7 = models.CharField(max_length=200, null=True, blank=True)
    request_return_url = models.CharField(max_length=500, null=True, blank=True)
    request_checksum = models.CharField(max_length=500, null=True, blank=True)
    request_string = models.TextField(null=True, blank=True)

    response_string = models.TextField(null=True, blank=True)
    response_merchantid = models.CharField(max_length=100, null=True, blank=True)
    response_customerid = models.CharField(max_length=100, null=True, blank=True)
    response_txnreferenceno = models.CharField(max_length=100, null=True, blank=True)
    response_bankreferenceno = models.CharField(max_length=100, null=True, blank=True)
    response_txnamount = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    response_bankid = models.CharField(max_length=50, null=True, blank=True)
    response_bankmerchantid = models.CharField(max_length=100, null=True, blank=True)
    response_txntype = models.CharField(max_length=50, null=True, blank=True)
    response_currencyname = models.CharField(max_length=10, null=True, blank=True)
    response_itemcode = models.CharField(max_length=50, null=True, blank=True)
    response_securitytype = models.CharField(max_length=50, null=True, blank=True)
    response_securityid = models.CharField(max_length=100, null=True, blank=True)
    response_securitypassword = models.CharField(max_length=100, null=True, blank=True)
    response_txndate = models.DateTimeField(null=True, blank=True)
    response_authstatus = models.CharField(max_length=10, null=True, blank=True)
    response_settlementtype = models.CharField(max_length=50, null=True, blank=True)
    response_additionalinfo1 = models.CharField(max_length=200, null=True, blank=True)
    response_additionalinfo2 = models.CharField(max_length=200, null=True, blank=True)
    response_additionalinfo3 = models.CharField(max_length=200, null=True, blank=True)
    response_additionalinfo4 = models.CharField(max_length=200, null=True, blank=True)
    response_additionalinfo5 = models.CharField(max_length=200, null=True, blank=True)
    response_additionalinfo6 = models.CharField(max_length=200, null=True, blank=True)
    response_additionalinfo7 = models.CharField(max_length=200, null=True, blank=True)
    response_errorstatus = models.CharField(max_length=50, null=True, blank=True)
    response_errordescription = models.CharField(max_length=500, null=True, blank=True)
    response_checksum = models.CharField(max_length=500, null=True, blank=True)
    response_checksum_calculated = models.CharField(max_length=500, null=True, blank=True)
    response_initial_authstatus = models.CharField(max_length=10, null=True, blank=True)
    response_initial_datetime = models.DateTimeField(null=True, blank=True)

    payment_status = models.CharField(max_length=1, default="P")
    user_id = models.CharField(max_length=50, null=True, blank=True)
    opr_date = models.DateTimeField(default=timezone.now)

    class Meta:
        managed = False
        db_table = "eabgari_payment_trsansaction_billdesk"

    def __str__(self):
        return f"{self.utr} ({self.payment_status})"


class PaymentHoaSplit(models.Model):
    id = models.BigAutoField(primary_key=True)
    transaction_id_no = models.CharField(max_length=50)
    head_of_account = models.CharField(max_length=50)
    payer_id = models.CharField(max_length=50)
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    payment_module_code = models.CharField(max_length=20, null=True, blank=True)
    requisition_id_no = models.CharField(max_length=50, null=True, blank=True)
    user_id = models.CharField(max_length=50, null=True, blank=True)
    opr_date = models.DateTimeField(default=timezone.now)

    class Meta:
        managed = False
        db_table = "eabgari_payment_send_hoa"


class PaymentStatusMasterBilldesk(models.Model):
    authstatus = models.CharField(max_length=10, primary_key=True)
    authstatus_description = models.CharField(max_length=500)
    payment_status = models.CharField(max_length=1)
    created_date = models.DateTimeField(default=timezone.now)

    class Meta:
        managed = False
        db_table = "eabgari_payment_status_master_billdesk"

    def __str__(self):
        return f"{self.authstatus} -> {self.payment_status}"


class PaymentBilldeskFdrParameter(models.Model):
    id = models.BigAutoField(primary_key=True)
    payment_module_code = models.CharField(max_length=20)
    requisition_id_no = models.CharField(max_length=50)
    request_additionalinfo1 = models.CharField(max_length=200, null=True, blank=True)
    request_additionalinfo2 = models.CharField(max_length=200, null=True, blank=True)
    request_additionalinfo3 = models.CharField(max_length=200, null=True, blank=True)
    request_additionalinfo4 = models.CharField(max_length=200, null=True, blank=True)
    request_additionalinfo5 = models.CharField(max_length=200, null=True, blank=True)
    request_additionalinfo6 = models.CharField(max_length=200, null=True, blank=True)
    request_additionalinfo7 = models.CharField(max_length=200, null=True, blank=True)
    created_date = models.DateTimeField(default=timezone.now)
    created_by = models.CharField(max_length=50, null=True, blank=True)

    class Meta:
        managed = False
        db_table = "eabgari_payment_billdesk_fdr_parameters"


class PaymentWalletMaster(models.Model):
    id = models.BigAutoField(primary_key=True)
    licensee_id_no = models.CharField(max_length=50)
    head_of_account = models.CharField(max_length=50)
    wallet_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    created_date = models.DateTimeField(default=timezone.now)
    modified_date = models.DateTimeField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = "eabgari_pay_wallet_master"


class PaymentWalletTransaction(models.Model):
    id = models.BigAutoField(primary_key=True)
    implementing_state_code = models.CharField(max_length=10, default="28")
    wallet_transaction_date = models.DateTimeField(default=timezone.now)
    wallet_transaction_type = models.CharField(max_length=1)
    licensee_id_no = models.CharField(max_length=50)
    head_of_account = models.CharField(max_length=50)
    transaction_amount = models.DecimalField(max_digits=18, decimal_places=2)
    transaction_reference_number = models.CharField(max_length=100)
    wallet_transaction_status = models.CharField(max_length=1, default="Y")
    initialization_flag = models.CharField(max_length=1, default="T")
    bank_utr = models.CharField(max_length=100, null=True, blank=True)
    payment_module_code = models.CharField(max_length=20, null=True, blank=True)
    transaction_remarks = models.CharField(max_length=500, null=True, blank=True)
    user_id = models.CharField(max_length=50, null=True, blank=True)
    opr_date = models.DateTimeField(default=timezone.now)

    class Meta:
        managed = False
        db_table = "eabgari_pay_wallet_transaction"


class PaymentHeadOfAccount(models.Model):
    head_of_account = models.CharField(max_length=50, primary_key=True)
    sl_no = models.BigIntegerField(unique=True, null=True, blank=True)
    major_head = models.CharField(max_length=10)
    sub_major_head = models.CharField(max_length=10, null=True, blank=True)
    minor_head = models.CharField(max_length=10)
    sub_head = models.CharField(max_length=10, null=True, blank=True)
    detailed_head = models.CharField(max_length=20)
    object_head = models.CharField(max_length=10, null=True, blank=True)
    detailed_head_driscription = models.CharField(max_length=500)
    pay_type = models.CharField(max_length=20, null=True, blank=True)
    visible_status = models.CharField(max_length=1, default="Y")
    created_date = models.DateTimeField(default=timezone.now)
    modified_date = models.DateTimeField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = "eabgari_master_head_of_accounts"

    def __str__(self):
        return self.head_of_account


class PaymentModule(models.Model):
    module_code = models.CharField(max_length=20, primary_key=True)
    module_desc = models.CharField(max_length=200)
    visibility_status = models.CharField(max_length=1, default="Y")
    active_payment_mode = models.CharField(max_length=1, default="O")
    payment_invoking_page = models.CharField(max_length=500, null=True, blank=True)
    payment_response_page = models.CharField(max_length=500, null=True, blank=True)
    user_id = models.CharField(max_length=50, null=True, blank=True)
    opr_date = models.DateTimeField(null=True, blank=True)
    created_date = models.DateTimeField(default=timezone.now)
    modified_date = models.DateTimeField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = "eabgari_master_module"

    def __str__(self):
        return f"{self.module_code} - {self.module_desc}"


class PaymentModuleHoa(models.Model):
    id = models.BigAutoField(primary_key=True)
    module_code = models.ForeignKey(
        PaymentModule,
        on_delete=models.RESTRICT,
        db_column="module_code",
        to_field="module_code",
    )
    head_of_account = models.ForeignKey(
        PaymentHeadOfAccount,
        on_delete=models.RESTRICT,
        db_column="head_of_account",
        to_field="head_of_account",
    )
    user_id = models.CharField(max_length=50, null=True, blank=True)
    opr_date = models.DateTimeField(default=timezone.now)
    is_active = models.CharField(max_length=1, default="Y")
    created_date = models.DateTimeField(default=timezone.now)

    class Meta:
        managed = False
        db_table = "eabgari_module_hoa"


class PaymentWalletTransactionHistory(models.Model):
    wallet_txn_id = models.BigAutoField(primary_key=True)
    user_id = models.CharField(max_length=50)
    transaction_type = models.CharField(max_length=200)
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    reference_id = models.CharField(max_length=100)
    status = models.CharField(max_length=50)
    created_at = models.DateTimeField(default=timezone.now)
    licensee_id = models.CharField(max_length=50, null=True, blank=True)
    approved_by = models.CharField(max_length=50, null=True, blank=True)
    permitnumber = models.CharField(max_length=100, null=True, blank=True)
    last_updated_date = models.DateTimeField(null=True, blank=True)
    remarks = models.CharField(max_length=500, null=True, blank=True)

    class Meta:
        managed = False
        db_table = "wallet_transaction_history"
