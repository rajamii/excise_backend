from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("ena_requisition_details", "0005_alter_bulk_liter_detail_requisition_fk"),
    ]

    operations = [
        migrations.RunSQL(
            sql=[
                # Older schema (OneToOne requisition) created a unique constraint/index on requisition_id.
                # Some DBs can retain it even after AlterField -> ForeignKey, causing duplicate-key failures.
                "ALTER TABLE reqution_bulk_liter_details DROP CONSTRAINT IF EXISTS reqution_bulk_liter_details_requisition_id_key;",
                "DROP INDEX IF EXISTS reqution_bulk_liter_details_requisition_id_key;",
            ],
            reverse_sql=[
                # Best-effort restore (legacy behavior): re-add unique on requisition_id.
                "CREATE UNIQUE INDEX IF NOT EXISTS reqution_bulk_liter_details_requisition_id_key ON reqution_bulk_liter_details (requisition_id);",
            ],
        ),
    ]

