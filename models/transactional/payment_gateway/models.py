from django.db import models
from django.utils import timezone


class PaymentGatewayParameters(models.Model):
    sl_no = models.IntegerField(primary_key=True)
    payment_gateway_name = models.CharField(max_length=50)
    merchantid = models.CharField(max_length=100)
    securityid = models.CharField(max_length=100)
    encryption_key = models.CharField(max_length=255)
    return_url = models.CharField(max_length=500)
    is_active = models.CharField(max_length=1, default="Y")
    created_date = models.DateTimeField(default=timezone.now)
    modified_date = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "Payment_Gateway_Parameters"

    def __str__(self) -> str:
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
        db_table = "sems_payment_transaction_billdesk"

    def __str__(self):
        return f"{self.utr} ({self.payment_status})"


# Formerly eAbgari_Payment_Send_HOA (pre-payment intent)
class PaymentSendHOA(models.Model):
    id = models.BigAutoField(primary_key=True)
    transaction_id_no = models.CharField(max_length=50)
    head_of_account = models.CharField(max_length=50)
    licensee_id = models.CharField(max_length=50, null=True, blank=True)
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    payment_module_code = models.CharField(max_length=20, null=True, blank=True)
    requisition_id_no = models.CharField(max_length=50, null=True, blank=True)
    user_id = models.CharField(max_length=50, null=True, blank=True)
    opr_date = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "sems_payment_send_hoa"
