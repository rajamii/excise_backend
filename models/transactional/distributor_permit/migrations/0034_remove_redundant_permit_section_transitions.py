from django.db import migrations


def clean_imfl_permit_section_transitions(apps, schema_editor):
    Workflow = apps.get_model('workflow', 'Workflow')
    WorkflowTransition = apps.get_model('workflow', 'WorkflowTransition')

    wf = Workflow.objects.filter(name__icontains="IMFL Requisition").first()
    if not wf:
        wf = Workflow.objects.filter(id=14).first()

    if wf:
        # Remove redundant APPROVE and VERIFY transitions for permit-section
        # Leaving only FORWARD and REJECT for permit-section
        for t in list(WorkflowTransition.objects.filter(workflow=wf)):
            cond = t.condition or {}
            role = str(cond.get('role') or '').lower()
            act = str(cond.get('action') or '').upper()
            if 'permit' in role and act in ('APPROVE', 'VERIFY'):
                from_name = str(t.from_stage.name or '').lower()
                if 'permit' in from_name or 'pending' in from_name or 'payslip' in from_name:
                    t.delete()


def reverse_func(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('distributor_permit', '0033_seed_imfl_payslip_transitions'),
    ]

    operations = [
        migrations.RunPython(clean_imfl_permit_section_transitions, reverse_func),
    ]
