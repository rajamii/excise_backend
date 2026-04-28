from django.db import migrations


def seed_rejected_stage(apps, schema_editor):
    Workflow = apps.get_model("workflow", "Workflow")
    WorkflowStage = apps.get_model("workflow", "WorkflowStage")

    workflow = Workflow.objects.filter(id=1).first()
    if not workflow:
        return

    # Ensure a final "Rejected" stage exists for workflow_id=1.
    stage = WorkflowStage.objects.filter(workflow_id=workflow.id, name__iexact="Rejected").first()
    if stage:
        updates = {}
        if stage.is_final is not True:
            updates["is_final"] = True
        if stage.is_initial is True:
            updates["is_initial"] = False
        if not stage.description:
            updates["description"] = "Application Rejected"
        if updates:
            for k, v in updates.items():
                setattr(stage, k, v)
            stage.save(update_fields=list(updates.keys()))
        return

    WorkflowStage.objects.create(
        workflow_id=workflow.id,
        name="Rejected",
        description="Application Rejected",
        is_initial=False,
        is_final=True,
    )


def unseed_rejected_stage(apps, schema_editor):
    Workflow = apps.get_model("workflow", "Workflow")
    WorkflowStage = apps.get_model("workflow", "WorkflowStage")

    workflow = Workflow.objects.filter(id=1).first()
    if not workflow:
        return

    # Only remove the stage if it matches our seed signature.
    WorkflowStage.objects.filter(
        workflow_id=workflow.id,
        name="Rejected",
        description="Application Rejected",
        is_initial=False,
        is_final=True,
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("workflow", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_rejected_stage, reverse_code=unseed_rejected_stage),
    ]

