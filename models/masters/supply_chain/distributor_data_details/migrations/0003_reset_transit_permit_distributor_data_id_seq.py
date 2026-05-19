from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('distributor_data_details', '0002_transitpermitdistributordata_license'),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
            -- Fix Postgres sequence drift when rows were inserted manually.
            SELECT setval(
                pg_get_serial_sequence('transit_permit_distributor_data', 'id'),
                COALESCE((SELECT MAX(id) FROM transit_permit_distributor_data), 0),
                true
            );
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]

