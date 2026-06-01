from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('license_renewal_application', '0004_remove_licenseapplication_license_app_excise__a9c318_idx_and_more'),
    ]

    operations = [
        migrations.AlterModelTable(
            name='licenseapplication',
            table='license_renewal_application',
        ),
    ]
