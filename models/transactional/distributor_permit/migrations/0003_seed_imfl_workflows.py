from django.db import migrations, connection


def seed_imfl_workflows(apps, schema_editor):
    Workflow = apps.get_model('workflow', 'Workflow')
    WorkflowStage = apps.get_model('workflow', 'WorkflowStage')
    WorkflowTransition = apps.get_model('workflow', 'WorkflowTransition')
    StagePermission = apps.get_model('workflow', 'StagePermission')

    def reset_sequences():
        with connection.cursor() as cursor:
            tables = ['workflow_workflow', 'workflow_workflowstage', 'workflow_workflowtransition', 'workflow_stagepermission']
            for table in tables:
                try:
                    cursor.execute(f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), COALESCE(MAX(id), 1)) FROM {table};")
                except Exception:
                    pass

    reset_sequences()

    # 1. IMFL Requisition
    req_wf, _ = Workflow.objects.get_or_create(
        name="IMFL Requisition",
        defaults={"description": "Workflow for IMFL Requisition"}
    )

    ena_req = Workflow.objects.filter(id=3).first()
    if not ena_req:
        ena_req = Workflow.objects.filter(name__icontains="ENA Requisition").first()

    stage_map_req = {}
    if ena_req:
        for s in ena_req.stages.all():
            new_s, _ = WorkflowStage.objects.get_or_create(
                workflow=req_wf,
                name=s.name,
                defaults={
                    "description": s.description or f"Stage {s.name} for IMFL Requisition",
                    "is_initial": s.is_initial,
                    "is_final": s.is_final
                }
            )
            stage_map_req[s.id] = new_s
            for p in StagePermission.objects.filter(stage=s):
                StagePermission.objects.get_or_create(stage=new_s, role=p.role, defaults={"can_process": p.can_process})

        for t in WorkflowTransition.objects.filter(workflow=ena_req):
            if t.from_stage_id in stage_map_req and t.to_stage_id in stage_map_req:
                WorkflowTransition.objects.get_or_create(
                    workflow=req_wf,
                    from_stage=stage_map_req[t.from_stage_id],
                    to_stage=stage_map_req[t.to_stage_id],
                    condition=t.condition
                )

    # 2. IMFL Revalidation
    reval_wf, _ = Workflow.objects.get_or_create(
        name="IMFL Revalidation",
        defaults={"description": "Workflow for IMFL Revalidation"}
    )

    ena_reval = Workflow.objects.filter(id=4).first()
    if not ena_reval:
        ena_reval = Workflow.objects.filter(name__icontains="ENA Revalidation").first()

    stage_map_reval = {}
    if ena_reval:
        for s in ena_reval.stages.all():
            new_s, _ = WorkflowStage.objects.get_or_create(
                workflow=reval_wf,
                name=s.name,
                defaults={
                    "description": s.description or f"Stage {s.name} for IMFL Revalidation",
                    "is_initial": s.is_initial,
                    "is_final": s.is_final
                }
            )
            stage_map_reval[s.id] = new_s
            for p in StagePermission.objects.filter(stage=s):
                StagePermission.objects.get_or_create(stage=new_s, role=p.role, defaults={"can_process": p.can_process})

        for t in WorkflowTransition.objects.filter(workflow=ena_reval):
            if t.from_stage_id in stage_map_reval and t.to_stage_id in stage_map_reval:
                WorkflowTransition.objects.get_or_create(
                    workflow=reval_wf,
                    from_stage=stage_map_reval[t.from_stage_id],
                    to_stage=stage_map_reval[t.to_stage_id],
                    condition=t.condition
                )

    # 3. IMFL Cancellation
    canc_wf, _ = Workflow.objects.get_or_create(
        name="IMFL Cancellation",
        defaults={"description": "Workflow for IMFL Cancellation"}
    )

    ena_canc = Workflow.objects.filter(id=5).first()
    if not ena_canc:
        ena_canc = Workflow.objects.filter(name__icontains="ENA Cancellation").first()

    stage_map_canc = {}
    if ena_canc:
        for s in ena_canc.stages.all():
            new_s, _ = WorkflowStage.objects.get_or_create(
                workflow=canc_wf,
                name=s.name,
                defaults={
                    "description": s.description or f"Stage {s.name} for IMFL Cancellation",
                    "is_initial": s.is_initial,
                    "is_final": s.is_final
                }
            )
            stage_map_canc[s.id] = new_s
            for p in StagePermission.objects.filter(stage=s):
                StagePermission.objects.get_or_create(stage=new_s, role=p.role, defaults={"can_process": p.can_process})

        for t in WorkflowTransition.objects.filter(workflow=ena_canc):
            if t.from_stage_id in stage_map_canc and t.to_stage_id in stage_map_canc:
                WorkflowTransition.objects.get_or_create(
                    workflow=canc_wf,
                    from_stage=stage_map_canc[t.from_stage_id],
                    to_stage=stage_map_canc[t.to_stage_id],
                    condition=t.condition
                )

    reset_sequences()


def reverse_func(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('distributor_permit', '0002_rename_distributor_applica_266aad_idx_imfl_brands_applica_ca5571_idx_and_more'),
    ]

    operations = [
        migrations.RunPython(seed_imfl_workflows, reverse_func),
    ]
