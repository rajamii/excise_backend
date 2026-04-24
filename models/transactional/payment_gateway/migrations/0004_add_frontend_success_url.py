from django.db import migrations, models


DEFAULT_FRONTEND_SUCCESS_URL = "http://localhost:4200/dashboard/wallet-recharge/success"


def seed_frontend_success_url(apps, schema_editor):
    PaymentGatewayParameters = apps.get_model("payment_gateway", "PaymentGatewayParameters")
    rows = PaymentGatewayParameters.objects.filter(payment_gateway_name__iexact="Billdesk")
    for row in rows:
        current = str(getattr(row, "frontend_success_url", "") or "").strip()
        if not current:
            row.frontend_success_url = DEFAULT_FRONTEND_SUCCESS_URL
            row.save(update_fields=["frontend_success_url"])


class Migration(migrations.Migration):
    dependencies = [
        ("payment_gateway", "0003_payment_send_hoa"),
    ]

    operations = [
        migrations.AddField(
            model_name="paymentgatewayparameters",
            name="frontend_success_url",
            field=models.CharField(blank=True, max_length=500, null=True),
        ),
        migrations.RunPython(seed_frontend_success_url, migrations.RunPython.noop),
    ]

