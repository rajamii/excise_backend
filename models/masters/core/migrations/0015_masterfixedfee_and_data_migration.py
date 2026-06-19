import django.utils.timezone
from django.db import migrations, models


def migrate_fixed_fees(apps, schema_editor):
    MasterPaymentModule = apps.get_model("payment_gateway", "MasterPaymentModule")
    MasterFixedFee = apps.get_model("core", "MasterFixedFee")

    target_codes = ["012", "NLI_ADD_DRAUGHT_BEER", "NLI_ADD_PACHWAI"]
    payment_modules = MasterPaymentModule.objects.filter(module_code__in=target_codes)
    pm_dict = {pm.module_code: pm for pm in payment_modules}

    # "012": Salesman/Barman Registration
    pm_012 = pm_dict.get("012")
    MasterFixedFee.objects.update_or_create(
        fee_code="012",
        defaults={
            "fee_desc": pm_012.module_desc if pm_012 else "Salesman/Barman Registration",
            "amount": pm_012.license_fee if pm_012 and pm_012.license_fee is not None else 3000.00,
            "is_active": pm_012.visibility_status if pm_012 else True,
        }
    )

    # "NLI_ADD_DRAUGHT_BEER": New License (Additional Charge) - Draught Beer
    pm_beer = pm_dict.get("NLI_ADD_DRAUGHT_BEER")
    MasterFixedFee.objects.update_or_create(
        fee_code="NLI_ADD_DRAUGHT_BEER",
        defaults={
            "fee_desc": pm_beer.module_desc if pm_beer else "New License (Additional Charge) - Draught Beer",
            "amount": pm_beer.license_fee if pm_beer and pm_beer.license_fee is not None else 5000.00,
            "is_active": pm_beer.visibility_status if pm_beer else True,
        }
    )

    # "NLI_ADD_PACHWAI": New License (Additional Charge) - Pachwai
    pm_pachwai = pm_dict.get("NLI_ADD_PACHWAI")
    MasterFixedFee.objects.update_or_create(
        fee_code="NLI_ADD_PACHWAI",
        defaults={
            "fee_desc": pm_pachwai.module_desc if pm_pachwai else "New License (Additional Charge) - Pachwai",
            "amount": pm_pachwai.license_fee if pm_pachwai and pm_pachwai.license_fee is not None else 3001.00,
            "is_active": pm_pachwai.visibility_status if pm_pachwai else True,
        }
    )

    # Delete from the old payment module table
    MasterPaymentModule.objects.filter(module_code__in=target_codes).delete()


def rollback_fixed_fees(apps, schema_editor):
    MasterPaymentModule = apps.get_model("payment_gateway", "MasterPaymentModule")
    MasterFixedFee = apps.get_model("core", "MasterFixedFee")

    target_codes = ["012", "NLI_ADD_DRAUGHT_BEER", "NLI_ADD_PACHWAI"]
    fixed_fees = MasterFixedFee.objects.filter(fee_code__in=target_codes)
    
    for ff in fixed_fees:
        MasterPaymentModule.objects.update_or_create(
            module_code=ff.fee_code,
            defaults={
                "module_desc": ff.fee_desc,
                "license_fee": ff.amount,
                "visibility_status": ff.is_active,
            }
        )
    
    MasterFixedFee.objects.filter(fee_code__in=target_codes).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0014_remove_additionalchargeconfig_amount'),
        ('payment_gateway', '0009_seed_additional_new_license_charges'),
    ]

    operations = [
        migrations.CreateModel(
            name='MasterFixedFee',
            fields=[
                ('fee_code', models.CharField(max_length=50, primary_key=True, serialize=False)),
                ('fee_desc', models.CharField(max_length=200)),
                ('amount', models.DecimalField(decimal_places=2, max_digits=18)),
                ('is_active', models.BooleanField(default=True)),
                ('created_date', models.DateTimeField(default=django.utils.timezone.now)),
                ('modified_date', models.DateTimeField(blank=True, null=True)),
            ],
            options={
                'db_table': 'masters_fixedfee',
            },
        ),
        migrations.RunPython(migrate_fixed_fees, rollback_fixed_fees),
    ]
