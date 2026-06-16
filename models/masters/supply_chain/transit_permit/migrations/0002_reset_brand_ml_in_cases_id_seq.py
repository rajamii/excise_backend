from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('transit_permit', '0001_initial'),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
            -- Fix Postgres sequence drift when rows were inserted manually.
            SELECT setval(
                pg_get_serial_sequence('brand_ml_in_cases', 'id'),
                COALESCE((SELECT MAX(id) FROM brand_ml_in_cases), 1),
                (CASE WHEN (SELECT MAX(id) FROM brand_ml_in_cases) IS NULL THEN false ELSE true END)
            );
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]

