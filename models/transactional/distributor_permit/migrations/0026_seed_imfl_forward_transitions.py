from django.db import migrations


def seed_imfl_transitions(apps, schema_editor):
    Workflow = apps.get_model('workflow', 'Workflow')
    WorkflowStage = apps.get_model('workflow', 'WorkflowStage')
    WorkflowTransition = apps.get_model('workflow', 'WorkflowTransition')

    wf = Workflow.objects.filter(name__icontains="IMFL Requisition").first()
    if not wf:
        wf = Workflow.objects.filter(id=14).first()

    if wf:
        stage_148 = WorkflowStage.objects.filter(id=148, workflow=wf).first() or WorkflowStage.objects.filter(name__icontains="Forwarded Permit Section", workflow=wf).first()
        stage_149 = WorkflowStage.objects.filter(id=149, workflow=wf).first() or WorkflowStage.objects.filter(name__iexact="Pending", workflow=wf).first()
        stage_153 = WorkflowStage.objects.filter(id=153, workflow=wf).first() or WorkflowStage.objects.filter(name__icontains="Forwarded Commissioner", workflow=wf).first()
        stage_152 = WorkflowStage.objects.filter(id=152, workflow=wf).first() or WorkflowStage.objects.filter(name__iexact="Rejected", workflow=wf).first()

        # Transitions from 148
        if stage_148 and stage_153:
            WorkflowTransition.objects.get_or_create(
                workflow=wf,
                from_stage=stage_148,
                to_stage=stage_153,
                condition={'role': 'permit-section', 'action': 'APPROVE'}
            )
            WorkflowTransition.objects.get_or_create(
                workflow=wf,
                from_stage=stage_148,
                to_stage=stage_153,
                condition={'role': 'permit-section', 'action': 'FORWARD'}
            )
        if stage_148 and stage_152:
            WorkflowTransition.objects.get_or_create(
                workflow=wf,
                from_stage=stage_148,
                to_stage=stage_152,
                condition={'role': 'permit-section', 'action': 'REJECT'}
            )

        # Transitions from 149
        if stage_149 and stage_153:
            WorkflowTransition.objects.get_or_create(
                workflow=wf,
                from_stage=stage_149,
                to_stage=stage_153,
                condition={'role': 'permit-section', 'action': 'FORWARD'}
            )


def reverse_func(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('distributor_permit', '0025_imflretailerstockdetails'),
    ]

    operations = [
        migrations.RunPython(seed_imfl_transitions, reverse_func),
    ]
