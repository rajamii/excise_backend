from django.core.exceptions import ValidationError

from auth.workflow.models import WorkflowStage


def _is_salesman_barman_application(application) -> bool:
    return application.__class__.__name__.lower() == "salesmanbarmanmodel"


def _stage_name(stage) -> str:
    return str(getattr(stage, "name", "") or "").strip().lower()


def _is_paid(application) -> bool:
    # Primary flag used across the module to indicate the fee has been paid and
    # the application can be treated as fully approved.
    return bool(getattr(application, "is_approved", False))


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
        _stage_by_names(application, ["awaiting_payment", "Awaiting Registration Fee Payment", "Awaiting Payment"])
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


def route_approval_to_payment_stage(application, *, from_stage, target_stage, context=None):
    """
    Salesman/Barman flow:
    - Commissioner "APPROVE" should move to `awaiting_payment` when unpaid.
    - Only after successful fee payment should it reach final `approved`.
    """
    if not _is_salesman_barman_application(application):
        return target_stage
    if _is_paid(application):
        return target_stage

    action = str((context or {}).get("action") or "").strip().upper()
    from_name = _stage_name(from_stage)
    to_name = _stage_name(target_stage)

    is_commissioner_approve = action == "APPROVE" and from_name in {"commissioner", "commisioner"}
    is_target_final_approval = bool(to_name == "approved" or getattr(target_stage, "is_final", False))
    if is_commissioner_approve and is_target_final_approval:
        return get_awaiting_payment_stage(application) or target_stage

    return target_stage


def enforce_salesman_barman_payment_gate(application, *, from_stage, target_stage, context=None):
    if not _is_salesman_barman_application(application):
        return
    if _is_paid(application):
        return

    awaiting = get_awaiting_payment_stage(application)
    from_name = _stage_name(from_stage)
    is_from_payment_gate = bool(
        (awaiting and getattr(from_stage, "id", None) == getattr(awaiting, "id", None))
        or from_name == "awaiting_payment"
        or ("awaiting" in from_name and "payment" in from_name)
        or ("payment" in from_name and "awaiting" in from_name)
    )
    if not is_from_payment_gate:
        return

    action = str((context or {}).get("action") or "").strip().upper()
    # Licensee should pay; other actions out of payment-gate should not "approve".
    if action != "PAY" and (_stage_name(target_stage) == "approved" or getattr(target_stage, "is_final", False)):
        raise ValidationError(
            "This application is awaiting registration fee payment. "
            "Approval is not allowed until payment is completed."
        )


def sync_salesman_barman_payment_status(application):
    """
    Keep `current_stage` aligned with `is_approved` after payment callbacks.
    """
    if not _is_salesman_barman_application(application):
        return

    update_fields = []
    if _is_paid(application):
        approved = get_approved_stage(application)
        if approved and application.current_stage_id != approved.id:
            application.current_stage = approved
            update_fields.append("current_stage")
    else:
        # If already at payment gate, normalize to `awaiting_payment` stage.
        awaiting = get_awaiting_payment_stage(application)
        cur_name = _stage_name(getattr(application, "current_stage", None))
        is_current_payment_gate = bool(
            (awaiting and application.current_stage_id == awaiting.id)
            or cur_name == "awaiting_payment"
            or ("payment" in cur_name and "reject" not in cur_name)
        )
        if awaiting and is_current_payment_gate and application.current_stage_id != awaiting.id:
            application.current_stage = awaiting
            update_fields.append("current_stage")

        if getattr(application, "is_approved", False):
            application.is_approved = False
            update_fields.append("is_approved")

    if update_fields:
        application.save(update_fields=update_fields)

