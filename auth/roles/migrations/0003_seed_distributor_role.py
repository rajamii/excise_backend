from django.db import migrations


def seed_distributor_role(apps, schema_editor):
    Role = apps.get_model('roles', 'Role')

    if Role.objects.filter(name__iexact='Distributor').exists():
        return

    Role.objects.create(
        id=16,
        name='Distributor',
        can_add=[],
        can_update=[],
        can_delete=[],
        can_view=[],
        role_precedence=2,
    )


class Migration(migrations.Migration):

    dependencies = [
        ('roles', '0002_backfill_company_registration_create'),
    ]

    operations = [
        migrations.RunPython(seed_distributor_role, reverse_code=migrations.RunPython.noop),
    ]
