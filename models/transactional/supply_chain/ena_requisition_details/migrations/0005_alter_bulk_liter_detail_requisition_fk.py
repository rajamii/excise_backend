from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('ena_requisition_details', '0004_bulk_liter_review_audit'),
    ]

    operations = [
        migrations.AlterField(
            model_name='requisitionbulkliterdetail',
            name='requisition',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='bulk_liter_details', to='ena_requisition_details.enarequisitiondetail'),
        ),
    ]

