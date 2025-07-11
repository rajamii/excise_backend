# Generated by Django 5.1.7 on 2025-07-10 05:08

import contact_us.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='DirectorateAndDistrictOfficials',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=255)),
                ('designation', models.CharField(max_length=255)),
                ('phone_number', models.CharField(blank=True, max_length=20, null=True)),
                ('email', models.EmailField(blank=True, max_length=254, null=True, validators=[contact_us.validators.validate_email])),
            ],
        ),
        migrations.CreateModel(
            name='GrievanceRedressalOfficer',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=255, validators=[contact_us.validators.validate_non_empty])),
                ('designation', models.CharField(max_length=255, validators=[contact_us.validators.validate_designation])),
                ('phone_number', models.CharField(default='00000000000', max_length=20, validators=[contact_us.validators.validate_phone_number])),
                ('email', models.EmailField(max_length=254, validators=[contact_us.validators.validate_email])),
                ('office_level', models.CharField(choices=[('Head Quarter', 'Head Quarter'), ('Permit Section', 'Permit Section'), ('Administration Section', 'Administration Section'), ('Field Section', 'Field Section'), ('Accounts Section', 'Accounts Section'), ('IT Cell', 'IT Cell')], default='Excise Head Office', max_length=255, validators=[contact_us.validators.validate_office_level])),
                ('office_sub_level', models.CharField(blank=True, max_length=255, null=True, validators=[contact_us.validators.validate_non_empty])),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='NodalOfficer',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('department', models.CharField(default='Excise Department', max_length=255, validators=[contact_us.validators.validate_department_name])),
                ('cell', models.CharField(default='IT Cell', max_length=255, null=True, validators=[contact_us.validators.validate_non_empty])),
                ('phone_number', models.CharField(default='(035) 9220-3963', max_length=20, validators=[contact_us.validators.validate_phone_number])),
                ('email', models.EmailField(default='helpdesk-excise@sikkim.gov.in', max_length=254, validators=[contact_us.validators.validate_email])),
            ],
        ),
        migrations.CreateModel(
            name='PublicInformationOfficer',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=255, validators=[contact_us.validators.validate_non_empty])),
                ('designation', models.CharField(max_length=255, validators=[contact_us.validators.validate_designation])),
                ('phone_number', models.CharField(default='00000000000', max_length=20, validators=[contact_us.validators.validate_phone_number])),
                ('email', models.EmailField(max_length=254, validators=[contact_us.validators.validate_email])),
                ('location_type', models.CharField(choices=[('Headquarter', 'Headquarter'), ('District', 'District'), ('unset', 'unset')], default='unset', max_length=20)),
                ('location', models.CharField(max_length=100)),
                ('address', models.CharField(default='Not Available', max_length=255)),
            ],
            options={
                'abstract': False,
            },
        ),
    ]
