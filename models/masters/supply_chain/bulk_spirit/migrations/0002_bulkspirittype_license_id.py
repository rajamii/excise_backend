from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("bulk_spirit", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="bulkspirittype",
            name="license_id",
            field=models.CharField(blank=True, db_index=True, max_length=50, null=True),
        ),
    ]

