import decimal
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('liquor_data', '0003_alter_masterliquorcapacity_options'),
    ]

    operations = [
        migrations.CreateModel(
            name='DistributorPermitApplication',
            fields=[
                ('reference_no', models.CharField(db_index=True, max_length=50, primary_key=True, serialize=False)),
                ('supplier_company_name', models.CharField(max_length=255)),
                ('logistics_partner', models.CharField(blank=True, default='', max_length=255)),
                ('source_address', models.TextField()),
                ('origin', models.TextField(blank=True, default='')),
                ('destination', models.TextField(blank=True, default='')),
                ('route_details', models.TextField(blank=True, default='')),
                ('declaration_accepted', models.BooleanField(default=False)),
                ('status', models.CharField(choices=[('Draft', 'Draft'), ('Submitted', 'Submitted')], default='Submitted', max_length=30)),
                ('officer_remarks', models.TextField(blank=True, default='')),
                ('submitted_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('applicant', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='distributor_permit_applications', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'db_table': 'distributor_permit_application',
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='DistributorPermitLineItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('brand_name', models.CharField(max_length=255)),
                ('size_ml', models.PositiveIntegerField()),
                ('pieces_per_case', models.PositiveIntegerField(default=0)),
                ('cases', models.PositiveIntegerField()),
                ('edp_per_case', models.DecimalField(decimal_places=2, default=decimal.Decimal('0.00'), max_digits=15)),
                ('import_pass_fee_per_case', models.DecimalField(decimal_places=2, default=decimal.Decimal('0.00'), max_digits=15)),
                ('mrp_per_bottle', models.DecimalField(decimal_places=2, default=decimal.Decimal('0.00'), max_digits=15)),
                ('additional_ed_per_case', models.DecimalField(decimal_places=2, default=decimal.Decimal('0.00'), max_digits=15)),
                ('education_cess_per_case', models.DecimalField(decimal_places=2, default=decimal.Decimal('0.00'), max_digits=15)),
                ('total_import', models.DecimalField(decimal_places=2, default=decimal.Decimal('0.00'), max_digits=15)),
                ('total_education_cess', models.DecimalField(decimal_places=2, default=decimal.Decimal('0.00'), max_digits=15)),
                ('total_additional_ed', models.DecimalField(decimal_places=2, default=decimal.Decimal('0.00'), max_digits=15)),
                ('bulk_litres', models.DecimalField(decimal_places=3, default=decimal.Decimal('0.000'), max_digits=15)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('application', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='line_items', to='distributor_permit.distributorpermitapplication')),
                ('brand', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='distributor_permit_line_items', to='liquor_data.masterbrandlist')),
            ],
            options={
                'db_table': 'distributor_permit_line_item',
                'ordering': ['id'],
            },
        ),
        migrations.CreateModel(
            name='DistributorPermitDocument',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('document_type', models.CharField(max_length=100)),
                ('file', models.FileField(upload_to='distributor_permits/')),
                ('uploaded_at', models.DateTimeField(auto_now_add=True)),
                ('application', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='documents', to='distributor_permit.distributorpermitapplication')),
            ],
            options={
                'db_table': 'distributor_permit_document',
                'ordering': ['id'],
            },
        ),
        migrations.AddIndex(
            model_name='distributorpermitapplication',
            index=models.Index(fields=['applicant'], name='distributor_applica_006404_idx'),
        ),
        migrations.AddIndex(
            model_name='distributorpermitapplication',
            index=models.Index(fields=['status'], name='distributor_status_55e8f7_idx'),
        ),
        migrations.AddIndex(
            model_name='distributorpermitapplication',
            index=models.Index(fields=['submitted_at'], name='distributor_submitt_76f2b4_idx'),
        ),
        migrations.AddIndex(
            model_name='distributorpermitlineitem',
            index=models.Index(fields=['application'], name='distributor_applica_266aad_idx'),
        ),
        migrations.AddIndex(
            model_name='distributorpermitlineitem',
            index=models.Index(fields=['brand'], name='distributor_brand_i_d3fd55_idx'),
        ),
    ]
