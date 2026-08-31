from django.db import migrations

def seed_additional_excise_wallet_type(apps, schema_editor):
    MasterWalletType = apps.get_model('wallet', 'MasterWalletType')
    MasterWalletType.objects.get_or_create(
        code='additional_excise',
        defaults={
            'name': 'Additional Excise Duty',
            'description': 'Additional Excise Duty Wallet Category',
            'is_active': True
        }
    )

class Migration(migrations.Migration):

    dependencies = [
        ('wallet', '0006_link_legacy_wallet_utrs'),
    ]

    operations = [
        migrations.RunPython(seed_additional_excise_wallet_type, reverse_code=migrations.RunPython.noop),
    ]
