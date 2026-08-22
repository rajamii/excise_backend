from django.db import migrations


def configure_secretary_role(apps, schema_editor):
    Role = apps.get_model('roles', 'Role')
    DashboardRoleConfig = apps.get_model('roles', 'DashboardRoleConfig')

    secretary_role = Role.objects.filter(id=11).first()
    if not secretary_role:
        secretary_role = Role.objects.filter(name__iexact='Secretary').first()

    if not secretary_role:
        secretary_role = Role.objects.create(
            id=11,
            name='Secretary',
            can_add=[],
            can_update=[],
            can_delete=[],
            can_view=[],
            role_precedence=9,
        )
    else:
        secretary_role.name = 'Secretary'
        secretary_role.can_add = []
        secretary_role.can_update = []
        secretary_role.can_delete = []
        secretary_role.can_view = []
        secretary_role.role_precedence = 9
        secretary_role.save()

    DashboardRoleConfig.objects.update_or_create(
        role=secretary_role,
        defaults={
            'layout': 'admin',
            'widgets': [],
            'navigation': [
                {'label': 'Dashboard', 'route': '/dashboard', 'icon': 'dashboard'}
            ],
            'permissions': [
                'dashboard.view'
            ],
            'is_active': True,
            'config_version': 1,
        },
    )


class Migration(migrations.Migration):

    dependencies = [
        ('roles', '0004_configure_distributor_dashboard'),
    ]

    operations = [
        migrations.RunPython(configure_secretary_role, reverse_code=migrations.RunPython.noop),
    ]
