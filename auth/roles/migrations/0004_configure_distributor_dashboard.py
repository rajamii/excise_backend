from django.db import migrations


def configure_distributor_dashboard(apps, schema_editor):
    Role = apps.get_model('roles', 'Role')
    DashboardRoleConfig = apps.get_model('roles', 'DashboardRoleConfig')

    distributor_role = Role.objects.filter(name__iexact='Distributor').first()
    if not distributor_role:
        distributor_role = Role.objects.create(
            name='Distributor',
            can_add=[],
            can_update=[],
            can_delete=[],
            can_view=[],
            role_precedence=2,
        )

    DashboardRoleConfig.objects.update_or_create(
        role=distributor_role,
        defaults={
            'layout': 'admin',
            'widgets': [],
            'navigation': [
                {
                    'label': 'Dashboard',
                    'route': '/dashboard',
                    'icon': 'dashboard',
                },
                {
                    'label': 'Apply for Import Permit',
                    'route': '/dashboard?section=distributor-permit',
                    'section': 'distributor-permit',
                    'icon': 'assignment',
                },
                {
                    'label': 'Officer Activity',
                    'route': '/dashboard?section=officer-activity',
                    'section': 'officer-activity',
                    'icon': 'assignment',
                },
            ],
            'permissions': [
                'dashboard.view',
                'distributor_permit.view',
                'distributor_permit.create',
                'officer_activity.view',
            ],
            'is_active': True,
            'config_version': 1,
        },
    )


class Migration(migrations.Migration):

    dependencies = [
        ('roles', '0003_seed_distributor_role'),
    ]

    operations = [
        migrations.RunPython(configure_distributor_dashboard, reverse_code=migrations.RunPython.noop),
    ]
