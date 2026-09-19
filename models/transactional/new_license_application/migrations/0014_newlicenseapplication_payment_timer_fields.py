from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("new_license_application", "0013_alter_newlicenseapplication_road_name"),
    ]

    operations = [
        migrations.AddField(
            model_name="newlicenseapplication",
            name="awaiting_payment_entered_at",
            field=models.DateTimeField(
                blank=True,
                help_text="Timestamp when the application transitioned into Stage 23 (Awaiting Payment).",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="newlicenseapplication",
            name="payment_deadline_at",
            field=models.DateTimeField(
                blank=True,
                help_text="Deadline by which License Fee and Security Amount must be paid.",
                null=True,
            ),
        ),
    ]
