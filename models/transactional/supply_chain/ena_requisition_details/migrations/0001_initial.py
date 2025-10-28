from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name='EnaRequisitionDetail',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('application_id', models.CharField(db_index=True, max_length=64)),
                ('requisition_number', models.CharField(max_length=64, unique=True)),
                ('requested_on', models.DateField()),
                ('quantity_liters', models.DecimalField(decimal_places=3, max_digits=12)),
                ('status', models.CharField(default='PENDING', max_length=32)),
                ('remarks', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'db_table': 'ena_requisition_detail',
                'ordering': ['-created_at'],
            },
        ),
    ]


