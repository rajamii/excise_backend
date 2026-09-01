from django.db import migrations

def seed_distributor_payment_module_and_hoa(apps, schema_editor):
    MasterPaymentModule = apps.get_model("payment_gateway", "MasterPaymentModule")
    PaymentModuleHoa = apps.get_model("payment_gateway", "PaymentModuleHoa")
    MasterHeadOfAccount = apps.get_model("payment_gateway", "MasterHeadOfAccount")
    MasterWalletType = apps.get_model("wallet", "MasterWalletType")

    if schema_editor.connection.vendor == "postgresql":
        with schema_editor.connection.cursor() as cursor:
            cursor.execute(
                "SELECT setval(pg_get_serial_sequence('sems_module_hoa', 'id'), COALESCE((SELECT MAX(id) FROM sems_module_hoa), 1));"
            )

    dist_mod, _ = MasterPaymentModule.objects.update_or_create(
        module_code="019",
        defaults={
            "module_desc": "distributor",
            "visibility_status": True,
        }
    )

    hoa_map = {
        "excise": "0039-00-105-45-01",
        "education_cess": "0045-00-112-45-03",
        "hologram": "0039-00-800-45-01",
        "security_deposit": "non",
        "license_fee": "0039-00-800-45-02",
    }

    for wcode, hoacode in hoa_map.items():
        hoa_obj = MasterHeadOfAccount.objects.get(head_of_account=hoacode)
        w_type = MasterWalletType.objects.get(code=wcode)
        pmh = PaymentModuleHoa.objects.filter(module_code=dist_mod, wallet_type=w_type).first()
        if pmh:
            pmh.head_of_account = hoa_obj
            pmh.is_active = True
            pmh.save()
        else:
            PaymentModuleHoa.objects.create(
                module_code=dist_mod,
                wallet_type=w_type,
                head_of_account=hoa_obj,
                is_active=True
            )

def remove_distributor_payment_module_and_hoa(apps, schema_editor):
    MasterPaymentModule = apps.get_model("payment_gateway", "MasterPaymentModule")
    PaymentModuleHoa = apps.get_model("payment_gateway", "PaymentModuleHoa")
    
    dist_mod = MasterPaymentModule.objects.filter(module_code="019").first()
    if dist_mod:
        PaymentModuleHoa.objects.filter(module_code=dist_mod).delete()
        dist_mod.delete()

class Migration(migrations.Migration):

    dependencies = [
        ("payment_gateway", "0009_seed_additional_new_license_charges"),
        ("wallet", "0007_add_additional_excise_wallet_type"),
    ]

    operations = [
        migrations.RunPython(seed_distributor_payment_module_and_hoa, remove_distributor_payment_module_and_hoa),
    ]
