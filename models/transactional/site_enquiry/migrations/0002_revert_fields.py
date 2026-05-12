from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("site_enquiry", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="siteenquiryreport",
            name="is_reverted",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="siteenquiryreport",
            name="reverted_remarks",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="siteenquiryreport",
            name="reverted_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]

