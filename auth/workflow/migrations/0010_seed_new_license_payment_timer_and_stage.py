"""
Migration 0010: New License Payment Timer & Payment Auto-Rejection Stage

1. Seeds `NEW_LICENSE_PAYMENT_TIMER` timer config (default 7 days).
2. Creates "Rejected – No Action Taken by User at Payment Stage" terminal WorkflowStage
   in the License Approval workflow.
3. Creates WorkflowTransition from awaiting_payment (Stage 23) to the new rejected stage.
"""

from django.db import migrations

REJECTED_STAGE_NAME = "Rejected – No Action Taken by User at Payment Stage"
REJECTED_STAGE_DESC = (
    "Application automatically rejected because License Fee and Security Amount "
    "were not paid within the allowed timeframe at payment stage."
)

PAYMENT_TIMER_CODE = "NEW_LICENSE_PAYMENT_TIMER"
PAYMENT_TIMER_DAYS = 7
PAYMENT_TIMER_DESC = (
    "Time limit for applicant to complete License Fee and Security Amount "
    "payment at Stage 23 (Awaiting Payment)."
)


def seed_payment_timer_and_stage(apps, schema_editor):
    # 1. Seed NEW_LICENSE_PAYMENT_TIMER in SupplyChainTimerConfig
    SupplyChainTimerConfig = apps.get_model("core", "SupplyChainTimerConfig")
    SupplyChainTimerConfig.objects.update_or_create(
        code=PAYMENT_TIMER_CODE,
        defaults={
            "description": PAYMENT_TIMER_DESC,
            "delay_value": PAYMENT_TIMER_DAYS,
            "delay_unit": "day",
            "is_active": True,
        },
    )

    # 2. Create the rejected stage and transition in the License Approval workflow
    Workflow = apps.get_model("workflow", "Workflow")
    WorkflowStage = apps.get_model("workflow", "WorkflowStage")
    WorkflowTransition = apps.get_model("workflow", "WorkflowTransition")

    wf = Workflow.objects.filter(name__icontains="License Approval").first()
    if not wf:
        wf = Workflow.objects.filter(id=1).first()

    if wf:
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

        # Locate awaiting_payment stage
        awaiting_stage = WorkflowStage.objects.filter(
            workflow=wf,
            name__in=["awaiting_payment", "Awaiting Payment", "Awaiting License Fee Payment"],
        ).first()

        if awaiting_stage:
            WorkflowTransition.objects.get_or_create(
                workflow=wf,
                from_stage=awaiting_stage,
                to_stage=rejected_stage,
                defaults={"condition": {"action": "AUTO_REJECT_PAYMENT"}},
            )


def unseed_payment_timer_and_stage(apps, schema_editor):
    SupplyChainTimerConfig = apps.get_model("core", "SupplyChainTimerConfig")
    SupplyChainTimerConfig.objects.filter(code=PAYMENT_TIMER_CODE).delete()

    Workflow = apps.get_model("workflow", "Workflow")
    WorkflowStage = apps.get_model("workflow", "WorkflowStage")
    WorkflowTransition = apps.get_model("workflow", "WorkflowTransition")

    wf = Workflow.objects.filter(name__icontains="License Approval").first() or Workflow.objects.filter(id=1).first()
    if wf:
        rejected_stage = WorkflowStage.objects.filter(
            workflow=wf,
            name=REJECTED_STAGE_NAME,
        ).first()
        if rejected_stage:
            WorkflowTransition.objects.filter(workflow=wf, to_stage=rejected_stage).delete()
            rejected_stage.delete()


class Migration(migrations.Migration):

    dependencies = [
        ("workflow", "0009_objection_deadline_auto_reject_stage"),
        ("core", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_payment_timer_and_stage, reverse_code=unseed_payment_timer_and_stage),
    ]
