from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):
    dependencies = [
        ("ena_requisition_details", "0003_add_oic_edit_fields"),
    ]

    operations = [
        migrations.CreateModel(
            name="RequisitionBulkLiterReviewAudit",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("reference_no", models.CharField(db_index=True, max_length=50)),
                ("licensee_id", models.CharField(blank=True, db_index=True, max_length=50, null=True)),
                (
                    "last_status",
                    models.CharField(
                        choices=[("PENDING", "Pending"), ("APPROVED", "Approved"), ("REJECTED", "Rejected")],
                        db_index=True,
                        default="PENDING",
                        max_length=20,
                    ),
                ),
                ("reviewed_at", models.DateTimeField(blank=True, null=True)),
                ("reviewed_by", models.CharField(blank=True, default="", max_length=150)),
                ("review_remarks", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now, editable=False)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "requisition",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="bulk_liter_review_audit",
                        to="ena_requisition_details.enarequisitiondetail",
                    ),
                ),
            ],
            options={
                "db_table": "reqution_bulk_liter_review_audit",
                "ordering": ["-updated_at"],
            },
        ),
    ]

