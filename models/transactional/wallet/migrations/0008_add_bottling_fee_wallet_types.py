from django.db import migrations

def seed_bottling_fee_wallet_types(apps, schema_editor):
    MasterWalletType = apps.get_model('wallet', 'MasterWalletType')
    MasterWalletType.objects.get_or_create(
        code='transit_permit_bottling_fee',
        defaults={
            'name': 'Transit Permit Bottling Fee',
            'description': 'Transit Permit Bottling Fee Wallet Category',
            'is_active': True
        }
    )
    MasterWalletType.objects.get_or_create(
        code='bottling_fee',
        defaults={
            'name': 'Bottling Fee',
            'description': 'Bottling Fee Wallet Category',
            'is_active': True
        }
    )

class Migration(migrations.Migration):

    dependencies = [
        ('wallet', '0007_add_additional_excise_wallet_type'),
    ]

    operations = [
        migrations.RunPython(seed_bottling_fee_wallet_types, reverse_code=migrations.RunPython.noop),
    ]
