"""
Migration 0009: Objection Deadline & Auto-Rejection Stage

1. Adds `deadline_at` column to `workflow_objection` table.
2. Seeds an `OBJECTION_DEADLINE` timer config (default 7 days).
3. Creates a "Rejected - No Action Taken on Objection" terminal WorkflowStage
   in each of the 4 affected workflows.
4. Creates WorkflowTransition from each workflow's objection stage(s) to the
   new rejected stage.
"""

from django.db import migrations, models

# Workflows and their objection stage names (as seeded by earlier migrations)
OBJECTION_WORKFLOW_MAP = [
    ("License Approval",            "Objection"),
    ("Salesman Barman",             "Objection"),
    ("Company Registration",        "Objection"),
    ("License Renewal Application", "Objection"),
]

REJECTED_STAGE_NAME = "Rejected - No Action Taken on Objection"
REJECTED_STAGE_DESC = (
    "Application automatically rejected because no action was taken "
    "on the raised objection within the allowed timeframe."
)

OBJECTION_DEADLINE_CODE = "OBJECTION_DEADLINE"
OBJECTION_DEADLINE_DAYS = 7
OBJECTION_DEADLINE_DESC = (
    "Number of days an applicant has to resolve an objection raised by an admin. "
    "If no action is taken within this period the application is automatically "
    "moved to 'Rejected - No Action Taken on Objection'."
)


def seed_objection_deadline(apps, schema_editor):
    # 1. Seed OBJECTION_DEADLINE timer config
    SupplyChainTimerConfig = apps.get_model("core", "SupplyChainTimerConfig")
    SupplyChainTimerConfig.objects.get_or_create(
        code=OBJECTION_DEADLINE_CODE,
        defaults={
            "description": OBJECTION_DEADLINE_DESC,
            "delay_value": OBJECTION_DEADLINE_DAYS,
            "delay_unit": "day",
            "is_active": True,
        },
    )

    # 2. For each affected workflow, create the new rejected stage + transition
    Workflow = apps.get_model("workflow", "Workflow")
    WorkflowStage = apps.get_model("workflow", "WorkflowStage")
    WorkflowTransition = apps.get_model("workflow", "WorkflowTransition")

    for workflow_name, objection_stage_name in OBJECTION_WORKFLOW_MAP:
        wf = Workflow.objects.filter(name=workflow_name).first()
        if not wf:
            continue

        rejected_stage, _ = WorkflowStage.objects.get_or_create(
            workflow=wf,
            name=REJECTED_STAGE_NAME,
            defaults={
                "description": REJECTED_STAGE_DESC,
                "is_initial": False,
                "is_final": True,
            },
        )
        if not rejected_stage.is_final:
            rejected_stage.is_final = True
            rejected_stage.save(update_fields=["is_final"])

        objection_stage = WorkflowStage.objects.filter(
            workflow=wf,
            name__iexact=objection_stage_name,
        ).first()
        if objection_stage:
            WorkflowTransition.objects.get_or_create(
                workflow=wf,
                from_stage=objection_stage,
                to_stage=rejected_stage,
                defaults={"condition": {"action": "AUTO_REJECT_OBJECTION"}},
            )


def unseed_objection_deadline(apps, schema_editor):
    SupplyChainTimerConfig = apps.get_model("core", "SupplyChainTimerConfig")
    SupplyChainTimerConfig.objects.filter(code=OBJECTION_DEADLINE_CODE).delete()

    Workflow = apps.get_model("workflow", "Workflow")
    WorkflowStage = apps.get_model("workflow", "WorkflowStage")
    WorkflowTransition = apps.get_model("workflow", "WorkflowTransition")

    for workflow_name, _ in OBJECTION_WORKFLOW_MAP:
        wf = Workflow.objects.filter(name=workflow_name).first()
        if not wf:
            continue
        rejected_stage = WorkflowStage.objects.filter(
            workflow=wf,
            name=REJECTED_STAGE_NAME,
        ).first()
        if rejected_stage:
            WorkflowTransition.objects.filter(workflow=wf, to_stage=rejected_stage).delete()
            rejected_stage.delete()


class Migration(migrations.Migration):

    dependencies = [
        ("workflow", "0008_auto_20260709_1852"),
    ]

    operations = [
        migrations.AddField(
            model_name="objection",
            name="deadline_at",
            field=models.DateTimeField(
                blank=True,
                null=True,
                help_text=(
                    "Datetime by which this objection must be resolved. "
                    "Auto-set from the OBJECTION_DEADLINE timer config when the objection is raised. "
                    "If the applicant takes no action by this time the application is automatically "
                    "moved to 'Rejected - No Action Taken on Objection'."
                ),
            ),
        ),
        migrations.RunPython(seed_objection_deadline, reverse_code=unseed_objection_deadline),
    ]
