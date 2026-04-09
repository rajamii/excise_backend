from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("ena_requisition_details", "0002_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="requisitionbulkliterdetail",
            name="edited_by_oic",
            field=models.BooleanField(db_index=True, default=False),
        ),
        migrations.AddField(
            model_name="requisitionbulkliterdetail",
            name="edited_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="requisitionbulkliterdetail",
            name="edited_by",
            field=models.CharField(blank=True, default="", max_length=150),
        ),
    ]

