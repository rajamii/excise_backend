from django.db import migrations

def seed_permissions(apps, schema_editor):
    StagePermission = apps.get_model('workflow', 'StagePermission')
    WorkflowStage = apps.get_model('workflow', 'WorkflowStage')
    Role = apps.get_model('roles', 'Role')

    role_ps = Role.objects.filter(id=5).first()
    role_comm = Role.objects.filter(id=10).first()
    role_sec = Role.objects.filter(id=11).first()
    role_dc = Role.objects.filter(id=12).first()
    role_dist = Role.objects.filter(id=14).first()
    role_lic = Role.objects.filter(id=2).first()

    stage_roles = {
        148: [role_ps],
        153: [role_comm, role_sec, role_dc],
        154: [role_dist, role_lic],
        156: [role_ps],
        157: [role_comm, role_sec, role_dc],
        151: [role_comm, role_sec, role_dc],
    }

    for stage_id, roles in stage_roles.items():
        stage = WorkflowStage.objects.filter(id=stage_id).first()
        if not stage:
            continue
        for r in roles:
            if r:
                StagePermission.objects.get_or_create(
                    stage=stage,
                    role=r,
                    defaults={'can_process': True}
                )

def unseed_permissions(apps, schema_editor):
    pass

class Migration(migrations.Migration):

    dependencies = [
        ('distributor_permit', '0034_remove_redundant_permit_section_transitions'),
    ]

    operations = [
        migrations.RunPython(seed_permissions, unseed_permissions),
    ]
