from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('masters_company_collaboration', '0002_remove_liquortype_liquor_cat_and_more'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.AlterField(
                    model_name='liquorkind',
                    name='liquor_cat',
                    field=models.PositiveSmallIntegerField(db_column='liquor_cat_code'),
                ),
                migrations.AlterField(
                    model_name='liquorbrand',
                    name='liquor_cat',
                    field=models.PositiveSmallIntegerField(db_column='liquor_cat_code'),
                ),
                migrations.AlterField(
                    model_name='liquorbrand',
                    name='liquor_type',
                    field=models.PositiveBigIntegerField(db_column='liquor_type_id'),
                ),
            ],
        ),
    ]
