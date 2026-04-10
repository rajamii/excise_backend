from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('hologram', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='hologramrequest',
            name='rejection_reason',
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='hologramrequest',
            name='rejected_at',
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name='hologramrequest',
            name='rejected_by',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='rejected_hologram_requests',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]

