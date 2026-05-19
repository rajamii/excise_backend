from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ena_purpose', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='purpose',
            name='is_active',
            field=models.BooleanField(default=True),
        ),
    ]
