from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ena_checkpost', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='checkpost',
            name='is_active',
            field=models.BooleanField(default=True),
        ),
    ]
