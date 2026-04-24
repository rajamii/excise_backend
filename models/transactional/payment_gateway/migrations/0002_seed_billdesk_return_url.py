from django.db import migrations


DEFAULT_BILLDESK_RETURN_URL = (
    "https://excise.sikkim.gov.in/Payment_Gateway/BillDesk_Response_Landing.aspx"
)


def update_return_url(apps, schema_editor):
    PaymentGatewayParameters = apps.get_model("payment_gateway", "PaymentGatewayParameters")
    row = PaymentGatewayParameters.objects.filter(sl_no=1).first()
    if not row:
        return

    current = str(getattr(row, "return_url", "") or "").strip().lower()
    # If it was seeded for localhost callback, replace with the deployment-configured BillDesk Return_URL.
    if "127.0.0.1" in current or "localhost" in current:
        row.return_url = DEFAULT_BILLDESK_RETURN_URL
        row.save(update_fields=["return_url"])


class Migration(migrations.Migration):
    dependencies = [
        ("payment_gateway", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(update_return_url, migrations.RunPython.noop),
    ]

