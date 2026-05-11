from django.db import migrations


def seed_workflow2_objection(apps, schema_editor):
    Workflow = apps.get_model("workflow", "Workflow")
    WorkflowStage = apps.get_model("workflow", "WorkflowStage")
    WorkflowTransition = apps.get_model("workflow", "WorkflowTransition")

    workflow = Workflow.objects.filter(id=2).first()
    if not workflow:
        return

    stage = WorkflowStage.objects.filter(workflow_id=workflow.id, name__iexact="objection").first()
    if stage:
        updates = {}
        if stage.is_initial is True:
            updates["is_initial"] = False
        if stage.is_final is True:
            updates["is_final"] = False
        if not stage.description:
            updates["description"] = "Application in Objection"
        if updates:
            for k, v in updates.items():
                setattr(stage, k, v)
            stage.save(update_fields=list(updates.keys()))
    else:
        stage = WorkflowStage.objects.create(
            workflow_id=workflow.id,
            name="Objection",
            description="Application in Objection",
            is_initial=False,
            is_final=False,
        )

    from_stage_names = [
        "District User",
        "Site Enquiry Officer",
        "Joint Commissioner",
        "Commissioner",
    ]

    for from_name in from_stage_names:
        from_stage = WorkflowStage.objects.filter(workflow_id=workflow.id, name__iexact=from_name).first()
        if not from_stage:
            continue

        # IMPORTANT: Do not add role/role_id in condition because WorkflowService.raise_objection()
        # calls validate_transition(..., user=None).
        condition = {"has_objections": True, "action": "RAISE_OBJECTION"}

        if WorkflowTransition.objects.filter(
            workflow_id=workflow.id,
            from_stage_id=from_stage.id,
            to_stage_id=stage.id,
        ).exists():
            continue

        WorkflowTransition.objects.create(
            workflow_id=workflow.id,
            from_stage_id=from_stage.id,
            to_stage_id=stage.id,
            condition=condition,
        )


def unseed_workflow2_objection(apps, schema_editor):
    Workflow = apps.get_model("workflow", "Workflow")
    WorkflowStage = apps.get_model("workflow", "WorkflowStage")
    WorkflowTransition = apps.get_model("workflow", "WorkflowTransition")

    workflow = Workflow.objects.filter(id=2).first()
    if not workflow:
        return

    stage = WorkflowStage.objects.filter(workflow_id=workflow.id, name__iexact="objection").first()
    if not stage:
        return

    WorkflowTransition.objects.filter(workflow_id=workflow.id, to_stage_id=stage.id).delete()
    WorkflowStage.objects.filter(id=stage.id).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("workflow", "0003_objection_resolved_by"),
    ]

    operations = [
        migrations.RunPython(seed_workflow2_objection, reverse_code=unseed_workflow2_objection),
    ]

