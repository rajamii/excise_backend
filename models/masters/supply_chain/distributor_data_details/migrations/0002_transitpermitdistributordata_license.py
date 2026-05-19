from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('license', '0002_initial'),
        ('distributor_data_details', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='transitpermitdistributordata',
            name='license',
            field=models.ForeignKey(
                to='license.license',
                to_field='license_id',
                db_column='license_id',
                on_delete=django.db.models.deletion.PROTECT,
                blank=True,
                null=True,
                related_name='transit_permit_distributor_data',
            ),
        ),
    ]
