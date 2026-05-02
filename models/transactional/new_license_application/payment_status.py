from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.core.exceptions import ValidationError

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
    if name in {"approved", "commissioner", "commisioner"}:
        return True
    if ("commissioner" in name or "commisioner" in name) and "approv" in name:
        return True
    return bool(getattr(stage, "is_final", False))


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


def enforce_new_license_payment_gate(application, *, from_stage, target_stage):
    """
    Prevent officers from "approving" a new-license application out of an unpaid
    payment-gate stage (awaiting/payment stage). Payment endpoints should flip
    flags and call `sync_new_license_payment_status()` instead.
    """
    if not _is_new_license_application(application):
        return
    if _is_paid(application):
        return
    if not from_stage or not target_stage:
        return

    awaiting = get_awaiting_payment_stage(application)
    from_name = _stage_name(from_stage)
    is_from_payment_gate = bool(
        (awaiting and getattr(from_stage, "id", None) == getattr(awaiting, "id", None))
        or ("awaiting" in from_name and "payment" in from_name)
        or (from_name == "awaiting_payment")
    )
    if not is_from_payment_gate:
        return

    if _is_approval_stage(target_stage):
        raise ValidationError(
            "This application is awaiting license fee/security payment. "
            "Approval is not allowed until payment is completed."
        )


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


def _text(value) -> str:
    return str(value or "").strip()


def _looks_like_manufacturing_license(license_obj) -> bool:
    category = getattr(license_obj, "license_category", None)
    sub_category = getattr(license_obj, "license_sub_category", None)

    category_name = _text(
        getattr(category, "license_category", None)
        or getattr(category, "category_name", None)
    ).lower()
    sub_category_name = _text(
        getattr(sub_category, "description", None)
        or getattr(sub_category, "license_sub_category", None)
        or getattr(sub_category, "subcategory_name", None)
    ).lower()

    is_manufacturing = "manufactur" in category_name
    is_factory_subcategory = (
        "distill" in sub_category_name
        or "brew" in sub_category_name
        or "beer" in sub_category_name
    )
    return bool(is_manufacturing and is_factory_subcategory)


def sync_master_factory_for_license(license_obj):
    if not license_obj or not getattr(license_obj, "is_active", False):
        return None
    if getattr(license_obj, "source_type", None) != "new_license_application":
        return None
    if not _looks_like_manufacturing_license(license_obj):
        return None

    application = getattr(license_obj, "source_application", None)
    factory_name = _text(getattr(application, "establishment_name", None))
    if not factory_name:
        return None

    from models.masters.supply_chain.liquor_data.models import MasterFactoryList

    license_ct = ContentType.objects.get_for_model(license_obj.__class__)
    factory, _ = MasterFactoryList.objects.update_or_create(
        factory_name=factory_name,
        defaults={
            "source_content_type": license_ct,
            "source_object_id": str(license_obj.license_id),
            "is_sync": 0,
        },
    )
    return factory


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
        sync_master_factory_for_license(license_obj)

    return license_obj
