from django.db import migrations, models
import django.utils.timezone


def seed_billdesk(apps, schema_editor):
    PaymentGatewayParameters = apps.get_model("payment_gateway", "PaymentGatewayParameters")
    PaymentGatewayParameters.objects.update_or_create(
        sl_no=1,
        defaults={
            "payment_gateway_name": "Billdesk",
            "merchantid": "ABEDPTM",
            "securityid": "abedptm",
            "encryption_key": "4DViVOCXzpWSfdeEUYI7Ofrj0cYtITiG",
            "return_url": "http://127.0.0.1:8000/transactional/payment-gateway/billdesk/response/",
            "is_active": "Y",
        },
    )


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="PaymentGatewayParameters",
            fields=[
                ("sl_no", models.IntegerField(primary_key=True, serialize=False)),
                ("payment_gateway_name", models.CharField(max_length=50)),
                ("merchantid", models.CharField(max_length=100)),
                ("securityid", models.CharField(max_length=100)),
                ("encryption_key", models.CharField(max_length=255)),
                ("return_url", models.CharField(max_length=500)),
                ("is_active", models.CharField(default="Y", max_length=1)),
                ("created_date", models.DateTimeField(default=django.utils.timezone.now)),
                ("modified_date", models.DateTimeField(blank=True, null=True)),
            ],
            options={
                "db_table": "Payment_Gateway_Parameters",
            },
        ),
        migrations.CreateModel(
            name="PaymentBilldeskTransaction",
            fields=[
                ("utr", models.CharField(max_length=100, primary_key=True, serialize=False)),
                ("transaction_date", models.DateTimeField(default=django.utils.timezone.now)),
                ("transaction_id_no_hoa", models.CharField(max_length=50)),
                ("payer_id", models.CharField(max_length=50)),
                ("payment_module_code", models.CharField(max_length=20)),
                ("transaction_amount", models.DecimalField(decimal_places=2, max_digits=18)),
                ("request_merchantid", models.CharField(blank=True, max_length=100, null=True)),
                ("request_currencytype", models.CharField(blank=True, max_length=10, null=True)),
                ("request_typefield1", models.CharField(blank=True, max_length=10, null=True)),
                ("request_securityid", models.CharField(blank=True, max_length=100, null=True)),
                ("request_typefield2", models.CharField(blank=True, max_length=10, null=True)),
                ("request_additionalinfo1", models.CharField(blank=True, max_length=200, null=True)),
                ("request_additionalinfo2", models.CharField(blank=True, max_length=200, null=True)),
                ("request_additionalinfo3", models.CharField(blank=True, max_length=200, null=True)),
                ("request_additionalinfo4", models.CharField(blank=True, max_length=200, null=True)),
                ("request_additionalinfo5", models.CharField(blank=True, max_length=200, null=True)),
                ("request_additionalinfo6", models.CharField(blank=True, max_length=200, null=True)),
                ("request_additionalinfo7", models.CharField(blank=True, max_length=200, null=True)),
                ("request_return_url", models.CharField(blank=True, max_length=500, null=True)),
                ("request_checksum", models.CharField(blank=True, max_length=500, null=True)),
                ("request_string", models.TextField(blank=True, null=True)),
                ("response_string", models.TextField(blank=True, null=True)),
                ("response_merchantid", models.CharField(blank=True, max_length=100, null=True)),
                ("response_customerid", models.CharField(blank=True, max_length=100, null=True)),
                ("response_txnreferenceno", models.CharField(blank=True, max_length=100, null=True)),
                ("response_bankreferenceno", models.CharField(blank=True, max_length=100, null=True)),
                ("response_txnamount", models.DecimalField(blank=True, decimal_places=2, max_digits=18, null=True)),
                ("response_bankid", models.CharField(blank=True, max_length=50, null=True)),
                ("response_bankmerchantid", models.CharField(blank=True, max_length=100, null=True)),
                ("response_txntype", models.CharField(blank=True, max_length=50, null=True)),
                ("response_currencyname", models.CharField(blank=True, max_length=10, null=True)),
                ("response_itemcode", models.CharField(blank=True, max_length=50, null=True)),
                ("response_securitytype", models.CharField(blank=True, max_length=50, null=True)),
                ("response_securityid", models.CharField(blank=True, max_length=100, null=True)),
                ("response_securitypassword", models.CharField(blank=True, max_length=100, null=True)),
                ("response_txndate", models.DateTimeField(blank=True, null=True)),
                ("response_authstatus", models.CharField(blank=True, max_length=10, null=True)),
                ("response_settlementtype", models.CharField(blank=True, max_length=50, null=True)),
                ("response_additionalinfo1", models.CharField(blank=True, max_length=200, null=True)),
                ("response_additionalinfo2", models.CharField(blank=True, max_length=200, null=True)),
                ("response_additionalinfo3", models.CharField(blank=True, max_length=200, null=True)),
                ("response_additionalinfo4", models.CharField(blank=True, max_length=200, null=True)),
                ("response_additionalinfo5", models.CharField(blank=True, max_length=200, null=True)),
                ("response_additionalinfo6", models.CharField(blank=True, max_length=200, null=True)),
                ("response_additionalinfo7", models.CharField(blank=True, max_length=200, null=True)),
                ("response_errorstatus", models.CharField(blank=True, max_length=50, null=True)),
                ("response_errordescription", models.CharField(blank=True, max_length=500, null=True)),
                ("response_checksum", models.CharField(blank=True, max_length=500, null=True)),
                ("response_checksum_calculated", models.CharField(blank=True, max_length=500, null=True)),
                ("response_initial_authstatus", models.CharField(blank=True, max_length=10, null=True)),
                ("response_initial_datetime", models.DateTimeField(blank=True, null=True)),
                ("payment_status", models.CharField(default="P", max_length=1)),
                ("user_id", models.CharField(blank=True, max_length=50, null=True)),
                ("opr_date", models.DateTimeField(default=django.utils.timezone.now)),
            ],
            options={
                "db_table": "sems_payment_transaction_billdesk",
            },
        ),
        migrations.RunPython(seed_billdesk, migrations.RunPython.noop),
    ]
