from django.db import migrations, connection


def seed_imfl_hologram_procurement_workflow(apps, schema_editor):
    Workflow = apps.get_model('workflow', 'Workflow')
    WorkflowStage = apps.get_model('workflow', 'WorkflowStage')
    WorkflowTransition = apps.get_model('workflow', 'WorkflowTransition')
    StagePermission = apps.get_model('workflow', 'StagePermission')
    Role = apps.get_model('roles', 'Role')

    def reset_sequences():
        with connection.cursor() as cursor:
            tables = ['workflow_workflow', 'workflow_workflowstage', 'workflow_workflowtransition', 'workflow_stagepermission']
            for table in tables:
                try:
                    cursor.execute(f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), COALESCE(MAX(id), 1)) FROM {table};")
                except Exception:
                    pass

    reset_sequences()

    # Find or create Role mappings
    roles = {r.name.lower(): r for r in Role.objects.all()}
    it_cell_role = roles.get('it cell') or roles.get('it_cell') or Role.objects.filter(id=6).first()
    commissioner_role = roles.get('commissioner') or Role.objects.filter(id=10).first()
    distributor_role = roles.get('distributor') or roles.get('licensee') or Role.objects.filter(id=16).first()

    # 1. Create IMFL Hologram Procurement Workflow
    wf, created = Workflow.objects.get_or_create(
        name="IMFL Hologram Procurement",
        defaults={"description": "Workflow for IMFL Distributor Hologram Procurement"}
    )

    # 2. Define Stages
    stages_config = [
        {"name": "Submitted", "is_initial": True, "is_final": False, "role": distributor_role},
        {"name": "Under IT Cell Review", "is_initial": False, "is_final": False, "role": it_cell_role},
        {"name": "Forwarded to Commissioner", "is_initial": False, "is_final": False, "role": commissioner_role},
        {"name": "Approved for Payment", "is_initial": False, "is_final": False, "role": distributor_role},
        {"name": "Payment Completed", "is_initial": False, "is_final": False, "role": it_cell_role},
        {"name": "Under IT Cell Review (Post-Payment)", "is_initial": False, "is_final": False, "role": it_cell_role},
        {"name": "Forwarded to Commissioner (Final)", "is_initial": False, "is_final": False, "role": commissioner_role},
        {"name": "Approved by Commissioner", "is_initial": False, "is_final": True, "role": commissioner_role},
        {"name": "Rejected by IT Cell", "is_initial": False, "is_final": True, "role": it_cell_role},
        {"name": "Rejected by Commissioner", "is_initial": False, "is_final": True, "role": commissioner_role},
    ]

    stage_objs = {}
    for cfg in stages_config:
        stage, _ = WorkflowStage.objects.get_or_create(
            workflow=wf,
            name=cfg["name"],
            defaults={
                "description": f"Stage {cfg['name']} for IMFL Hologram Procurement",
                "is_initial": cfg["is_initial"],
                "is_final": cfg["is_final"]
            }
        )
        stage_objs[cfg["name"]] = stage
        if cfg["role"]:
            StagePermission.objects.get_or_create(stage=stage, role=cfg["role"], defaults={"can_process": True})

    # 3. Define Transitions
    transitions_config = [
        # Distributor -> IT Cell
        ("Submitted", "Under IT Cell Review", {"role": "it_cell", "role_id": 6, "action": "forward"}),
        ("Submitted", "Forwarded to Commissioner", {"role": "it_cell", "role_id": 6, "action": "forward"}),
        ("Submitted", "Rejected by IT Cell", {"role": "it_cell", "role_id": 6, "action": "reject"}),
        
        # IT Cell -> Commissioner
        ("Under IT Cell Review", "Forwarded to Commissioner", {"role": "it_cell", "role_id": 6, "action": "forward"}),
        ("Under IT Cell Review", "Rejected by IT Cell", {"role": "it_cell", "role_id": 6, "action": "reject"}),
        
        # Commissioner -> Payment
        ("Forwarded to Commissioner", "Approved for Payment", {"role": "commissioner", "role_id": 10, "action": "approve"}),
        ("Forwarded to Commissioner", "Rejected by Commissioner", {"role": "commissioner", "role_id": 10, "action": "reject"}),
        
        # Payment -> IT Cell Post-Payment
        ("Approved for Payment", "Payment Completed", {"role": "distributor", "role_id": 16, "action": "pay"}),
        ("Payment Completed", "Under IT Cell Review (Post-Payment)", {"role": "it_cell", "role_id": 6, "action": "forward"}),
        ("Payment Completed", "Forwarded to Commissioner (Final)", {"role": "it_cell", "role_id": 6, "action": "forward"}),
        
        # IT Cell Post-Payment -> Commissioner Final
        ("Under IT Cell Review (Post-Payment)", "Forwarded to Commissioner (Final)", {"role": "it_cell", "role_id": 6, "action": "forward"}),
        ("Under IT Cell Review (Post-Payment)", "Rejected by IT Cell", {"role": "it_cell", "role_id": 6, "action": "reject"}),
        
        # Commissioner Final -> Completed
        ("Forwarded to Commissioner (Final)", "Approved by Commissioner", {"role": "commissioner", "role_id": 10, "action": "approve"}),
        ("Forwarded to Commissioner (Final)", "Rejected by Commissioner", {"role": "commissioner", "role_id": 10, "action": "reject"}),
    ]

    for from_name, to_name, cond in transitions_config:
        from_st = stage_objs.get(from_name)
        to_st = stage_objs.get(to_name)
        if from_st and to_st:
            WorkflowTransition.objects.get_or_create(
                workflow=wf,
                from_stage=from_st,
                to_stage=to_st,
                defaults={"condition": cond}
            )


class Migration(migrations.Migration):

    dependencies = [
        ('distributor_permit', '0027_imflhologramprocurement'),
    ]

    operations = [
        migrations.RunPython(seed_imfl_hologram_procurement_workflow, migrations.RunPython.noop),
    ]
