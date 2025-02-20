# Generated by Django 5.1.6 on 2025-02-19 06:08

import django.db.models.deletion
import excise_app.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('masters', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='LicenseType',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('licenseType', models.CharField(default=None, max_length=200)),
            ],
        ),
        migrations.CreateModel(
            name='State',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('State', models.CharField(default='Sikkim')),
                ('StateNameLL', models.CharField(max_length=30, validators=[excise_app.validators.validate_name])),
                ('StateCode', models.IntegerField(default=11, unique=True)),
                ('IsActive', models.BooleanField(default=True)),
            ],
        ),
        migrations.CreateModel(
            name='District',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('District', models.CharField(max_length=30, validators=[excise_app.validators.validate_name])),
                ('DistrictNameLL', models.CharField(max_length=30, null=True, validators=[excise_app.validators.validate_name])),
                ('DistrictCode', models.IntegerField(default=117, unique=True)),
                ('IsActive', models.BooleanField(default=True)),
                ('StateCode', models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='districts', to='masters.state', to_field='StateCode')),
            ],
        ),
        migrations.CreateModel(
            name='Subdivision',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('SubDivisionName', models.CharField(max_length=30, null=True, validators=[excise_app.validators.validate_name])),
                ('SubDivisionNameLL', models.CharField(max_length=30, null=True, validators=[excise_app.validators.validate_name])),
                ('SubDivisionCode', models.IntegerField(default=1001, unique=True)),
                ('IsActive', models.BooleanField(default=True)),
                ('DistrictCode', models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='subdivisions', to='masters.district', to_field='DistrictCode')),
            ],
        ),
        migrations.CreateModel(
            name='PoliceStation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('PoliceStationName', models.CharField(max_length=30, null=True, validators=[excise_app.validators.validate_name])),
                ('PoliceStationCode', models.IntegerField(default=11999, unique=True)),
                ('IsActive', models.BooleanField(default=True)),
                ('SubDivisionCode', models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='policestation', to='masters.subdivision', to_field='SubDivisionCode')),
            ],
        ),
    ]
