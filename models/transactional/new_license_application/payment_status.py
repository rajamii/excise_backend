from django.contrib.contenttypes.models import ContentType
from django.db import transaction

from auth.workflow.models import WorkflowStage
from models.masters.license.models import License


def _is_new_license_application(application) -> bool:
    return application.__class__.__name__.lower() == "newlicenseapplication"


def _is_paid(application) -> bool:
    return bool(
        getattr(application, "is_license_fee_paid", False)
        and getattr(application, "is_security_fee_paid", False)
    )


def _stage_name(stage) -> str:
    return str(getattr(stage, "name", "") or "").strip().lower()


def _is_approval_stage(stage) -> bool:
    name = _stage_name(stage)
    if not name or "reject" in name or "objection" in name:
        return False
    return bool(name == "approved" or getattr(stage, "is_final", False))


def _stage_by_names(application, names: list[str]):
    if not getattr(application, "workflow_id", None):
        return None
    for name in names:
        stage = (
            WorkflowStage.objects.filter(workflow_id=application.workflow_id, name__iexact=name)
            .order_by("id")
            .first()
        )
        if stage:
            return stage
    return None


def get_awaiting_payment_stage(application):
    if not getattr(application, "workflow_id", None):
        return None
    return (
        _stage_by_names(application, ["awaiting_payment", "Awaiting Payment"])
        or WorkflowStage.objects.filter(
            workflow_id=application.workflow_id,
            name__icontains="payment",
        )
        .exclude(name__icontains="reject")
        .order_by("id")
        .first()
    )


def get_approved_stage(application):
    if not getattr(application, "workflow_id", None):
        return None
    return (
        _stage_by_names(application, ["approved", "Approved"])
        or WorkflowStage.objects.filter(workflow_id=application.workflow_id, is_final=True)
        .exclude(name__icontains="reject")
        .order_by("id")
        .first()
    )


def route_approval_to_payment_stage(application, target_stage):
    if not _is_new_license_application(application):
        return target_stage
    if _is_paid(application):
        return target_stage
    if not _is_approval_stage(target_stage):
        return target_stage
    return get_awaiting_payment_stage(application) or target_stage


def resolve_license_for_application(application):
    new_app_ct = ContentType.objects.get_for_model(application.__class__)
    return (
        License.objects.filter(
            source_type="new_license_application",
            source_content_type=new_app_ct,
            source_object_id=str(application.pk),
        )
        .order_by("-issue_date", "-license_id")
        .first()
    )


@transaction.atomic
def sync_new_license_payment_status(application):
    if not _is_new_license_application(application):
        return None

    license_obj = resolve_license_for_application(application)
    paid = _is_paid(application)

    update_fields = []
    if paid:
        approved_stage = get_approved_stage(application)
        if approved_stage and application.current_stage_id != approved_stage.id:
            application.current_stage = approved_stage
            update_fields.append("current_stage")
        if not getattr(application, "is_approved", False):
            application.is_approved = True
            update_fields.append("is_approved")
    else:
        awaiting_stage = get_awaiting_payment_stage(application)
        if awaiting_stage and application.current_stage_id != awaiting_stage.id:
            application.current_stage = awaiting_stage
            update_fields.append("current_stage")
        if getattr(application, "is_approved", False):
            application.is_approved = False
            update_fields.append("is_approved")

    if update_fields:
        application.save(update_fields=update_fields)

    if license_obj and license_obj.is_active != paid:
        license_obj.is_active = paid
        license_obj.save(update_fields=["is_active"])

    if paid and license_obj:
        try:
            from models.transactional.wallet.wallet_initializer import (
                initialize_wallet_balances_for_license,
            )

            initialize_wallet_balances_for_license(license_obj)
        except Exception:
            pass

    return license_obj
