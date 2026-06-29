import django.db.models.deletion
from django.db import migrations, models

import models.transactional.label_registration.models as label_registration_models


def seed_label_registration_workflow(apps, schema_editor):
    Workflow = apps.get_model('workflow', 'Workflow')
    WorkflowStage = apps.get_model('workflow', 'WorkflowStage')
    WorkflowTransition = apps.get_model('workflow', 'WorkflowTransition')
    StagePermission = apps.get_model('workflow', 'StagePermission')
    Role = apps.get_model('roles', 'Role')

    workflow, _ = Workflow.objects.get_or_create(
        name='Label Registration',
        defaults={'description': 'Workflow for label registration applications'},
    )

    stage_defs = [
        ('applicant_applied', 'Application submitted by licensee', True, False),
        ('permit_section', 'Permit section review', False, False),
        ('permit_section_objection', 'Objection raised by permit section', False, False),
        ('deputy_commissioner', 'Deputy commissioner review', False, False),
        ('deputy_commissioner_objection', 'Objection raised by deputy commissioner', False, False),
        ('commissioner', 'Commissioner review', False, False),
        ('commissioner_objection', 'Objection raised by commissioner', False, False),
        ('approved', 'Approved', False, True),
        ('rejected', 'Rejected', False, True),
    ]

    stages = {}
    for name, description, is_initial, is_final in stage_defs:
        effective_initial = is_initial and not workflow.stages.exclude(name=name).filter(is_initial=True).exists()
        stage, _ = WorkflowStage.objects.get_or_create(
            workflow=workflow,
            name=name,
            defaults={
                'description': description,
                'is_initial': effective_initial,
                'is_final': is_final,
            },
        )
        updates = []
        if stage.description != description:
            stage.description = description
            updates.append('description')
        if stage.is_initial != effective_initial:
            stage.is_initial = effective_initial
            updates.append('is_initial')
        if stage.is_final != is_final:
            stage.is_final = is_final
            updates.append('is_final')
        if updates:
            stage.save(update_fields=updates)
        stages[name] = stage

    transitions = [
        ('applicant_applied', 'permit_section', {'action': 'SUBMIT', 'role': 'licensee'}),
        ('applicant_applied', 'permit_section', {'action': 'FORWARD', 'role': 'single_window'}),
        ('permit_section', 'deputy_commissioner', {'action': 'FORWARD', 'role': 'permit_section'}),
        ('permit_section', 'permit_section_objection', {'action': 'RAISE_OBJECTION', 'role': 'permit_section', 'has_objections': True}),
        ('permit_section', 'rejected', {'action': 'REJECT', 'role': 'permit_section'}),
        ('permit_section_objection', 'permit_section', {'action': 'RESPOND_OBJECTION', 'role': 'licensee'}),
        ('deputy_commissioner', 'commissioner', {'action': 'FORWARD', 'role': 'deputy_commissioner'}),
        ('deputy_commissioner', 'deputy_commissioner_objection', {'action': 'RAISE_OBJECTION', 'role': 'deputy_commissioner', 'has_objections': True}),
        ('deputy_commissioner', 'rejected', {'action': 'REJECT', 'role': 'deputy_commissioner'}),
        ('deputy_commissioner_objection', 'deputy_commissioner', {'action': 'RESPOND_OBJECTION', 'role': 'licensee'}),
        ('commissioner', 'approved', {'action': 'APPROVE', 'role': 'commissioner'}),
        ('commissioner', 'commissioner_objection', {'action': 'RAISE_OBJECTION', 'role': 'commissioner', 'has_objections': True}),
        ('commissioner', 'rejected', {'action': 'REJECT', 'role': 'commissioner'}),
        ('commissioner_objection', 'commissioner', {'action': 'RESPOND_OBJECTION', 'role': 'licensee'}),
    ]

    for from_name, to_name, condition in transitions:
        WorkflowTransition.objects.get_or_create(
            workflow=workflow,
            from_stage=stages[from_name],
            to_stage=stages[to_name],
            condition=condition,
        )

    role_stage_names = {
        'licensee': ['applicant_applied', 'permit_section_objection', 'deputy_commissioner_objection', 'commissioner_objection'],
        'license_user': ['applicant_applied', 'permit_section_objection', 'deputy_commissioner_objection', 'commissioner_objection'],
        'licensee_user': ['applicant_applied', 'permit_section_objection', 'deputy_commissioner_objection', 'commissioner_objection'],
        'single_window': ['applicant_applied'],
        'permit_section': ['permit_section'],
        'permit_excise': ['permit_section'],
        'deputy_commissioner': ['deputy_commissioner'],
        'joint_commissioner': ['deputy_commissioner'],
        'commissioner': ['commissioner'],
        'commissioner_excise': ['commissioner'],
        'site_admin': list(stages.keys()),
    }

    def normalize(value):
        return str(value or '').strip().lower().replace('-', '_').replace(' ', '_')

    for role in Role.objects.all():
        stage_names = role_stage_names.get(normalize(role.name), [])
        for stage_name in stage_names:
            StagePermission.objects.get_or_create(
                stage=stages[stage_name],
                role=role,
                defaults={'can_process': True},
            )


class Migration(migrations.Migration):

    dependencies = [
        ('workflow', '0002_seed_workflow1_rejected_stage'),
        ('label_registration', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='labelregistration',
            name='current_stage',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='label_registrations', to='workflow.workflowstage'),
        ),
        migrations.AddField(
            model_name='labelregistration',
            name='is_approved',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='labelregistration',
            name='upload_details',
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name='labelregistration',
            name='workflow',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='label_registrations', to='workflow.workflow'),
        ),
        migrations.CreateModel(
            name='LabelRegistrationDocument',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('document_key', models.CharField(max_length=80)),
                ('document_name', models.CharField(blank=True, max_length=255)),
                ('file', models.FileField(max_length=255, upload_to=label_registration_models.upload_document_path)),
                ('mime_type', models.CharField(blank=True, max_length=120)),
                ('uploaded_at', models.DateTimeField(auto_now_add=True)),
                ('application', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='documents', to='label_registration.labelregistration')),
            ],
            options={
                'db_table': 'label_registration_document',
                'ordering': ['document_key'],
                'unique_together': {('application', 'document_key')},
            },
        ),
        migrations.AddIndex(
            model_name='labelregistration',
            index=models.Index(fields=['current_stage'], name='label_reg_stage_idx'),
        ),
        migrations.RunPython(seed_label_registration_workflow, migrations.RunPython.noop),
    ]
