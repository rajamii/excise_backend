# Generated by Django 5.1.6 on 2025-03-11 07:10

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('excise_app', '0002_remove_customuser_user_id_alter_customuser_email'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='district',
            name='StateCode',
        ),
        migrations.RemoveField(
            model_name='subdivision',
            name='DistrictCode',
        ),
        migrations.DeleteModel(
            name='State',
        ),
        migrations.DeleteModel(
            name='District',
        ),
        migrations.DeleteModel(
            name='Subdivision',
        ),
    ]
