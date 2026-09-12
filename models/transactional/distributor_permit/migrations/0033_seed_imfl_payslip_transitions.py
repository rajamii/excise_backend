from django.db import migrations


def seed_imfl_payslip_transitions(apps, schema_editor):
    Workflow = apps.get_model('workflow', 'Workflow')
    WorkflowStage = apps.get_model('workflow', 'WorkflowStage')
    WorkflowTransition = apps.get_model('workflow', 'WorkflowTransition')

    wf = Workflow.objects.filter(name__icontains="IMFL Requisition").first()
    if not wf:
        wf = Workflow.objects.filter(id=14).first()

    if wf:
        stage_156 = WorkflowStage.objects.filter(id=156, workflow=wf).first() or WorkflowStage.objects.filter(name__icontains="PaySlip Permit Section", workflow=wf).first()
        stage_157 = WorkflowStage.objects.filter(id=157, workflow=wf).first() or WorkflowStage.objects.filter(name__icontains="PaySlip Commissioner", workflow=wf).first()
        stage_151 = WorkflowStage.objects.filter(id=151, workflow=wf).first() or WorkflowStage.objects.filter(name__iexact="Approved", workflow=wf).first()
        stage_152 = WorkflowStage.objects.filter(id=152, workflow=wf).first() or WorkflowStage.objects.filter(name__iexact="Rejected", workflow=wf).first()

        # Transitions from 156 (Permit Section reviewing payslip) -> 157 (Commissioner)
        if stage_156 and stage_157:
            for action in ('FORWARD', 'APPROVE', 'VERIFY'):
                WorkflowTransition.objects.get_or_create(
                    workflow=wf,
                    from_stage=stage_156,
                    to_stage=stage_157,
                    condition={'role': 'permit-section', 'action': action}
                )
        if stage_156 and stage_152:
            WorkflowTransition.objects.get_or_create(
                workflow=wf,
                from_stage=stage_156,
                to_stage=stage_152,
                condition={'role': 'permit-section', 'action': 'REJECT'}
            )

        # Transitions from 157 (Commissioner final review on payslip) -> 151 (Approved)
        if stage_157 and stage_151:
            WorkflowTransition.objects.get_or_create(
                workflow=wf,
                from_stage=stage_157,
                to_stage=stage_151,
                condition={'role': 'commissioner', 'action': 'APPROVE'}
            )
        if stage_157 and stage_152:
            WorkflowTransition.objects.get_or_create(
                workflow=wf,
                from_stage=stage_157,
                to_stage=stage_152,
                condition={'role': 'commissioner', 'action': 'REJECT'}
            )


def reverse_func(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('distributor_permit', '0032_imflhologramdetails_used_hologram_ranges'),
    ]

    operations = [
        migrations.RunPython(seed_imfl_payslip_transitions, reverse_func),
    ]
