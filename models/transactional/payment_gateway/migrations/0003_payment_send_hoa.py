from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):
    dependencies = [
        ("payment_gateway", "0002_seed_billdesk_return_url"),
    ]

    operations = [
        migrations.CreateModel(
            name="PaymentSendHOA",
            fields=[
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                ("transaction_id_no", models.CharField(max_length=50)),
                ("head_of_account", models.CharField(max_length=50)),
                ("licensee_id", models.CharField(blank=True, max_length=50, null=True)),
                ("amount", models.DecimalField(decimal_places=2, max_digits=18)),
                ("payment_module_code", models.CharField(blank=True, max_length=20, null=True)),
                ("requisition_id_no", models.CharField(blank=True, max_length=50, null=True)),
                ("user_id", models.CharField(blank=True, max_length=50, null=True)),
                ("opr_date", models.DateTimeField(default=django.utils.timezone.now)),
            ],
            options={
                "db_table": "sems_payment_send_hoa",
            },
        ),
    ]

