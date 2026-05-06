# Generated manually to match the about_us master module models

from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='ExciseSecretary',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('slNo', models.PositiveIntegerField(db_column='sl_no')),
                ('name', models.CharField(max_length=255)),
                ('fromDate', models.CharField(db_column='from_date', max_length=50)),
                ('toDate', models.CharField(db_column='to_date', max_length=50)),
            ],
            options={
                'ordering': ['slNo', 'id'],
            },
        ),
        migrations.CreateModel(
            name='HeadOfOrganisation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=255)),
                ('title', models.CharField(max_length=255)),
                ('image', models.CharField(max_length=500)),
            ],
        ),
    ]
