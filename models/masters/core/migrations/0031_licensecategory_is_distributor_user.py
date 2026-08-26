from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('core', '0030_remove_validity_period_days_from_timer'),
    ]

    operations = [
        migrations.AddField(
            model_name='licensecategory',
            name='is_distributor_user',
            field=models.BooleanField(default=False, help_text='Whether licensees of this category are distributor users (access to both Wallets and License tabs)'),
        ),
    ]
