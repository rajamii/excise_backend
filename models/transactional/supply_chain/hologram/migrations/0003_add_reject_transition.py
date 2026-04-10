from django.db import migrations


def _normalize_role_token(value: str) -> str:
    token = ''.join(ch for ch in str(value or '').lower() if ch.isalnum())
    if token in {'officerincharge', 'officercharge', 'oic', 'offcierincharge'}:
        return 'officer_in_charge'
    return token


def ensure_reject_transition(apps, schema_editor):
    Workflow = apps.get_model('workflow', 'Workflow')
    WorkflowStage = apps.get_model('workflow', 'WorkflowStage')
    WorkflowTransition = apps.get_model('workflow', 'WorkflowTransition')

    # Reset the transition PK sequence (some environments have it out of sync).
    try:
        schema_editor.execute(
            "SELECT setval("
            "  pg_get_serial_sequence('workflow_workflowtransition','id'),"
            "  COALESCE((SELECT MAX(id) FROM workflow_workflowtransition), 1) + 1,"
            "  false"
            ");"
        )
    except Exception:
        # Non-Postgres or missing privileges: ignore. ORM create may still work.
        pass

    workflow = Workflow.objects.filter(id=7).first() or Workflow.objects.filter(name__iexact='Hologram Request').first()
    if not workflow:
        return

    from_stage = WorkflowStage.objects.filter(workflow_id=workflow.id, name__iexact='Submitted').first()
    to_stage = WorkflowStage.objects.filter(workflow_id=workflow.id, name__iexact='Rejected by OIC').first()
    if not from_stage or not to_stage:
        return

    condition = {'role': 'officer_in_charge', 'action': 'reject'}

    obj = WorkflowTransition.objects.filter(workflow_id=workflow.id, from_stage_id=from_stage.id, to_stage_id=to_stage.id).first()
    if obj:
        obj.condition = condition
        obj.save(update_fields=['condition'])
        return

    WorkflowTransition.objects.create(
        workflow_id=workflow.id,
        from_stage_id=from_stage.id,
        to_stage_id=to_stage.id,
        condition=condition,
    )


class Migration(migrations.Migration):
    dependencies = [
        ('hologram', '0002_hologramrequest_rejection_fields'),
        ('workflow', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(ensure_reject_transition, migrations.RunPython.noop),
    ]
