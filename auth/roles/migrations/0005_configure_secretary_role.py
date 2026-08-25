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
                {'label': 'Dashboard', 'route': '/dashboard', 'icon': 'dashboard'},
                {'label': 'Bulk Spirit Overview', 'route': '/dashboard?section=secretary-bulk-spirit', 'section': 'secretary-bulk-spirit', 'icon': 'water_drop'},
                {'label': 'Licenses', 'route': '/dashboard?section=secretary-licenses', 'section': 'secretary-licenses', 'icon': 'verified'},
                {'label': 'IMFL', 'route': '/dashboard?section=secretary-imfl', 'section': 'secretary-imfl', 'icon': 'local_shipping'},
                {'label': 'Admin Activity', 'route': '/dashboard?section=officer-activity', 'section': 'officer-activity', 'icon': 'assignment'},
                {'label': 'Monthly View Details', 'route': '/dashboard?section=commissioner-monthly-view-details', 'section': 'commissioner-monthly-view-details', 'icon': 'calendar_month'}
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
