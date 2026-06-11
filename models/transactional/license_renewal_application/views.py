from django.shortcuts import get_object_or_404
from datetime import timedelta
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.parsers import JSONParser, FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import LicenseApplication
from .serializers import LicenseApplicationSerializer
from auth.workflow.models import Workflow
from auth.workflow.services import WorkflowService
from models.masters.license.models import License
from models.transactional.helpers import _normalize_role, _get_stage_sets, _get_role_stage_names
from models.masters.core.models import SupplyChainTimerConfig
from models.transactional.wallet.wallet_initializer import _resolve_hoa_code
from models.transactional.wallet.wallet_service import debit_wallet_balance
import secrets
from django.core.exceptions import PermissionDenied
from decimal import Decimal
from auth.workflow.models import Transaction as WorkflowTransaction
from auth.workflow.models import WorkflowStage


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_license_application(request):
    """
    Create a minimal license renewal record (stored in `license_application` table).
    """
    serializer = LicenseApplicationSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    obj = serializer.save()
    return Response(LicenseApplicationSerializer(obj).data, status=status.HTTP_201_CREATED)


def _get_renewal_workflow() -> Workflow | None:
    return (
        Workflow.objects.filter(name="License Renewal Application").order_by("id").first()
        or Workflow.objects.filter(name="License Approval").order_by("id").first()
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def initiate_renewal(request, license_id):
    """
    Create a renewal-tracking application (LRA/...) that follows the same stage machine
    as the New License workflow, but under the dedicated "License Renewal Application" workflow.
    """
    old_license = get_object_or_404(License, license_id=str(license_id))
    if old_license.applicant_id != request.user.id:
        return Response({"detail": "You can only renew your own license."}, status=status.HTTP_403_FORBIDDEN)

    now_dt = timezone.now()
    reminder_days = _get_timer_days("LICENSE_RENEWAL_REMINDER_TIMER", 90)

    # Best-effort: keep license status consistent once it crosses expiry.
    if getattr(old_license, "valid_up_to", None) and old_license.valid_up_to < now_dt and getattr(old_license, "is_active", True):
        old_license.is_active = False
        old_license.save(update_fields=["is_active"])

    # Flip fee-paid flags on source application to False when renewal starts, so they must pay again.
    src_app = _resolve_new_license_application_from_license(old_license)
    if src_app is not None:
        update_fields = ["is_license_fee_paid", "is_security_fee_paid"]
        
        pachwai = request.data.get("pachwai")
        if pachwai is not None:
            src_app.pachwai = bool(pachwai)
            update_fields.append("pachwai")
            
        draught_beer = request.data.get("draught_beer")
        if draught_beer is not None:
            src_app.draught_beer = bool(draught_beer)
            update_fields.append("draught_beer")
            
        mode_of_operation = request.data.get("mode_of_operation")
        if mode_of_operation is not None and mode_of_operation in ["Self", "Salesman", "Barman"]:
            if mode_of_operation in ["Salesman", "Barman"]:
                from models.transactional.salesman_barman.models import SalesmanBarmanModel
                from django.db.models import Q
                
                has_sbm = SalesmanBarmanModel.objects.filter(
                    Q(new_license_application=src_app) | Q(license=old_license) | Q(renewal_of=old_license),
                    applicant=request.user,
                    role__iexact=mode_of_operation
                ).exists()
                
                if not has_sbm:
                    return Response(
                        {"detail": f"Please register/fill the {mode_of_operation.lower()} application first to opt for {mode_of_operation.lower()}."},
                        status=status.HTTP_400_BAD_REQUEST
                    )

            src_app.mode_of_operation = str(mode_of_operation)
            update_fields.append("mode_of_operation")
            
            if mode_of_operation == "Self":
                from models.transactional.salesman_barman.models import SalesmanBarmanModel
                from auth.workflow.models import Transaction, Rejection
                from django.contrib.contenttypes.models import ContentType
                from django.db.models import Q
                
                # Query and terminate any active salesman/barman applications associated with this license
                sbm_apps = SalesmanBarmanModel.objects.filter(
                    Q(new_license_application=src_app) | Q(license=old_license) | Q(renewal_of=old_license),
                    applicant=request.user
                ).exclude(current_stage__name__iexact="rejected")
                
                for sbm_app in sbm_apps:
                    rejected_stage = sbm_app.workflow.stages.filter(name__iexact="rejected").order_by("id").first()
                    if rejected_stage:
                        sbm_app.current_stage = rejected_stage
                        sbm_app.is_approved = False
                        sbm_app.save(update_fields=["current_stage", "is_approved"])
                        
                        # Deactivate the associated License record(s)
                        License.objects.filter(
                            source_type="salesman_barman",
                            source_object_id=str(sbm_app.pk)
                        ).update(is_active=False)
                        
                        if getattr(sbm_app, "renewal_of", None):
                            License.objects.filter(
                                license_id=sbm_app.renewal_of.license_id
                            ).update(is_active=False)
                        
                        Rejection.objects.create(
                            content_type=ContentType.objects.get_for_model(sbm_app),
                            object_id=str(sbm_app.pk),
                            remarks="Rejected by user of salesman barman registration",
                            rejected_by=request.user,
                            stage=rejected_stage,
                        )
                        
                        Transaction.objects.create(
                            content_type=ContentType.objects.get_for_model(sbm_app),
                            object_id=str(sbm_app.pk),
                            performed_by=request.user,
                            forwarded_by=getattr(request.user, "role", None),
                            forwarded_to=None,
                            stage=rejected_stage,
                            remarks="Rejected by user of salesman barman registration",
                        )

        src_app.is_license_fee_paid = False
        src_app.is_security_fee_paid = False
        src_app.save(update_fields=update_fields)

    # Renewal window opens only within the reminder window (or after expiry).
    if getattr(old_license, "valid_up_to", None) and old_license.valid_up_to > now_dt + timedelta(days=reminder_days):
        window_start = old_license.valid_up_to - timedelta(days=reminder_days)
        window_end = old_license.valid_up_to
        return Response(
            {
                "detail": (
                    "Renewal not allowed yet. "
                    f"You can renew from {window_start.strftime('%d/%m/%Y')} "
                    f"to {window_end.strftime('%d/%m/%Y')}."
                ),
                "renewal_window_starts_on": window_start.isoformat(),
                "renewal_window_ends_on": window_end.isoformat(),
                "license_valid_up_to": old_license.valid_up_to.isoformat(),
                "reminder_window_days": reminder_days,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    wf = _get_renewal_workflow()
    if not wf:
        return Response({"detail": "Renewal workflow is not configured."}, status=status.HTTP_400_BAD_REQUEST)

    initial_stage = wf.stages.filter(is_initial=True).order_by("id").first()
    if not initial_stage:
        return Response({"detail": "Renewal workflow has no initial stage."}, status=status.HTTP_400_BAD_REQUEST)

    stage_sets = _get_stage_sets(wf.id)
    final_stages = set(stage_sets["approved"]) | set(stage_sets["rejected"])
    active_renewal = (
        LicenseApplication.objects.filter(
            applicant=request.user,
            old_license_id=old_license.license_id,
            workflow=wf,
        )
        .exclude(current_stage__name__in=final_stages)
        .order_by("-created_at")
        .first()
    )
    if active_renewal:
        return Response(
            {
                "detail": "A renewal application is already submitted for this license.",
                "application_id": active_renewal.application_id,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    district_code = str(getattr(getattr(old_license, "excise_district", None), "district_code", "") or "000").strip()
    fin_year = LicenseApplication.generate_fin_year()
    prefix = f"LRA/{district_code}/{fin_year}"

    last = (
        LicenseApplication.objects.filter(application_id__startswith=prefix + "/")
        .order_by("-application_id")
        .first()
    )
    last_number = 0
    if last and "/" in last.application_id:
        try:
            last_number = int(last.application_id.split("/")[-1])
        except Exception:
            last_number = 0
    new_number = str(last_number + 1).zfill(4)
    application_id = f"{prefix}/{new_number}"

    app = LicenseApplication.objects.create(
        application_id=application_id,
        is_approved=False,
        old_license_id=old_license.license_id,
        applicant=request.user,
        license_category=old_license.license_category,
        license_sub_category=old_license.license_sub_category,
        workflow=wf,
        current_stage=initial_stage,
    )

    WorkflowService.submit_application(application=app, user=request.user, remarks="Renewal application submitted")

    return Response(_serialize_renewal_application(app), status=status.HTTP_201_CREATED)


def _require_licensee_user(request):
    if not getattr(request.user, "is_authenticated", False):
        raise PermissionDenied("Authentication required.")
    role = _normalize_role(request.user.role.name if getattr(request.user, "role", None) else None)
    if role != "licensee":
        raise PermissionDenied("Only licensees can pay fees.")


def _get_timer_days(code: str, default_days: int) -> int:
    cfg = (
        SupplyChainTimerConfig.objects.filter(code=code, is_active=True)
        .order_by("-updated_at", "-id")
        .first()
    )
    if not cfg:
        return int(default_days)

    unit = str(getattr(cfg, "delay_unit", "") or "").lower().strip()
    value = getattr(cfg, "delay_value", None)
    try:
        value_int = max(0, int(value or 0))
    except (TypeError, ValueError):
        value_int = 0

    # Prefer configured unit/value (so changing delay_value/unit takes effect immediately),
    # fallback to validity_period_days if unit/value are missing or not meaningful.
    if value_int > 0 and unit:
        if unit.endswith("s"):
            unit = unit[:-1]
        if unit == "day":
            return value_int
        if unit in ("week", "wk"):
            return value_int * 7
        if unit in ("month", "mon", "mo"):
            return value_int * 30
        if unit in ("year", "yr"):
            return value_int * 365
        if unit in ("hour", "hr"):
            return max(0, value_int // 24)

    days = getattr(cfg, "validity_period_days", None)
    if days is not None:
        try:
            return max(0, int(days))
        except (TypeError, ValueError):
            return int(default_days)

    return int(default_days)


def _extend_license_validity(lic: License) -> License:
    from models.masters.core.models import RenewalApplicationConfig
    from datetime import date, datetime, time as dt_time
    from zoneinfo import ZoneInfo
    
    now_dt = timezone.now()
    base_dt = lic.valid_up_to if lic.valid_up_to and lic.valid_up_to > now_dt else now_dt
    
    config = RenewalApplicationConfig.objects.first()
    r_month = config.renewal_month if config else 3
    r_day = config.renewal_day if config else 31
    r_time = config.renewal_time if config else dt_time(23, 59, 59)
    
    # Convert base_dt to local timezone
    local_tz = ZoneInfo("Asia/Kolkata")
    local_base = timezone.localtime(base_dt, local_tz)
    
    base_renewal_date = date(local_base.year, r_month, r_day)
    if local_base.date() >= base_renewal_date:
        next_year = local_base.year + 1
    else:
        next_year = local_base.year
        
    next_valid_day = date(next_year, r_month, r_day)
    
    if isinstance(r_time, str):
        try:
            t_parts = r_time.split(":")
            r_time = dt_time(int(t_parts[0]), int(t_parts[1]), int(t_parts[2] if len(t_parts) > 2 else 0))
        except:
            r_time = dt_time(23, 59, 59)
            
    next_valid_dt = datetime.combine(next_valid_day, r_time)
    lic.valid_up_to = timezone.make_aware(next_valid_dt, local_tz) if timezone.is_naive(next_valid_dt) else next_valid_dt
    lic.save(update_fields=["valid_up_to"])
    return lic


def _sync_license_active_from_renewal_payment(lic: License, application: LicenseApplication) -> None:
    """
    Renewal activation rule:
    - license becomes active only after BOTH renewal payments are completed.
    - if not fully paid, keep it inactive (but validity may already be extended).
    """
    should_be_active = _renewal_is_paid(application)
    if should_be_active and not getattr(application, "is_approved", False):
        lic.is_active = True
        lic.print_count = 0
        lic.printed_on = None
        lic.is_print_fee_paid = False
        lic.print_fee_paid_on = None
        lic.validation_nonce = ''
        lic.validation_nonce_updated_at = None
        lic.save(update_fields=[
            "is_active",
            "print_count",
            "printed_on",
            "is_print_fee_paid",
            "print_fee_paid_on",
            "validation_nonce",
            "validation_nonce_updated_at"
        ])
    else:
        if bool(getattr(lic, "is_active", False)) != bool(should_be_active):
            lic.is_active = bool(should_be_active)
            lic.save(update_fields=["is_active"])


def _resolve_new_license_application_from_license(lic: License):
    if getattr(lic, "source_type", None) != "new_license_application":
        return None
    try:
        return lic.source_application
    except Exception:
        return None


def _renewal_source_application(application):
    old_license = None
    if getattr(application, "old_license_id", None):
        old_license = License.objects.filter(license_id=str(application.old_license_id)).first()
    if old_license is not None:
        source_app = _resolve_new_license_application_from_license(old_license)
        if source_app is not None:
            return source_app
    try:
        return application.source_object
    except Exception:
        return None


def _renewal_is_paid(application) -> bool:
    old_license = None
    if getattr(application, "old_license_id", None):
        old_license = License.objects.filter(license_id=str(application.old_license_id)).first()

    if old_license and old_license.source_type == "salesman_barman":
        return bool(getattr(application, "is_license_fee_paid", False))

    source_app = _renewal_source_application(application)
    app_license_paid = getattr(application, "is_license_fee_paid", False) or (source_app and getattr(source_app, "is_license_fee_paid", False))
    app_security_paid = getattr(application, "is_security_fee_paid", False) or (source_app and getattr(source_app, "is_security_fee_paid", False))
    return bool(source_app and app_license_paid and app_security_paid)


def _renewal_awaiting_payment_stage(application):
    if not getattr(application, "workflow_id", None):
        return None
    return (
        WorkflowStage.objects.filter(workflow_id=application.workflow_id, name__iexact="Awaiting Payment")
        .order_by("id")
        .first()
        or WorkflowStage.objects.filter(workflow_id=application.workflow_id, name__icontains="payment")
        .exclude(name__icontains="reject")
        .order_by("id")
        .first()
    )


def _renewal_approved_stage(application):
    if not getattr(application, "workflow_id", None):
        return None
    return (
        WorkflowStage.objects.filter(workflow_id=application.workflow_id, name__iexact="approved")
        .order_by("id")
        .first()
        or WorkflowStage.objects.filter(workflow_id=application.workflow_id, is_final=True)
        .exclude(name__icontains="reject")
        .order_by("id")
        .first()
    )


def _renewal_role_stage_names(user, workflow_id: int):
    role_stage_names = _get_role_stage_names(user, workflow_id)
    if role_stage_names:
        return role_stage_names

    role_token = _normalize_role(user.role.name if getattr(user, "role", None) else None)
    if not role_token:
        return set()

    stage_names = set(_get_stage_sets(workflow_id)["all"])
    aliases = {
        "district_user": ["district user"],
        "site_enquiry_officer": ["site enquiry officer"],
        "joint_commissioner": ["joint commissioner"],
        "commissioner": ["commissioner"],
        "secretary": ["secretary"],
    }
    tokens = aliases.get(role_token, [role_token.replace("_", " ")])
    matched = {name for name in stage_names if any(token in str(name).lower() for token in tokens)}
    if role_token == "commissioner":
        matched = {name for name in matched if "joint commissioner" not in str(name).lower()}
    return matched


def _renewal_queryset_visible_to_role(qs, user, role_stage_names):
    """
    Admin dashboards should only see renewal applications that are with their
    role now, or have already reached their role in the current submission cycle.
    """
    from django.contrib.contenttypes.models import ContentType
    from django.db.models import Exists, OuterRef, Q, Subquery

    role_id = getattr(getattr(user, "role", None), "id", None)
    if not role_id or not role_stage_names:
        return qs.none()

    content_type = ContentType.objects.get_for_model(LicenseApplication)
    latest_submission_id = (
        WorkflowTransaction.objects.filter(
            content_type=content_type,
            object_id=OuterRef("application_id"),
            stage__is_initial=True,
        )
        .order_by("-id")
        .values("id")[:1]
    )
    qs = qs.annotate(_latest_submission_id=Subquery(latest_submission_id))
    reached_role = Exists(
        WorkflowTransaction.objects.filter(
            content_type=content_type,
            object_id=OuterRef("application_id"),
            id__gte=OuterRef("_latest_submission_id"),
        ).filter(
            Q(performed_by__role_id=role_id)
            | Q(forwarded_to_id=role_id)
        )
    )

    return (
        qs.annotate(_reached_role=reached_role)
        .filter(Q(current_stage__name__in=role_stage_names) | Q(_reached_role=True))
    )


def _route_renewal_approval_to_payment_stage(application, target_stage):
    if _renewal_is_paid(application):
        return target_stage

    awaiting_payment_stage = _renewal_awaiting_payment_stage(application)
    if not awaiting_payment_stage:
        return target_stage

    target_name = str(getattr(target_stage, "name", "") or "").strip().lower()
    if "reject" in target_name or "objection" in target_name:
        return target_stage

    return awaiting_payment_stage


def _sync_renewal_payment_status(application):
    paid = _renewal_is_paid(application)
    update_fields = []

    if paid:
        approved_stage = _renewal_approved_stage(application)
        if approved_stage and application.current_stage_id != approved_stage.id:
            application.current_stage = approved_stage
            update_fields.append("current_stage")
        if not getattr(application, "is_approved", False):
            application.is_approved = True
            update_fields.append("is_approved")
    else:
        awaiting_stage = _renewal_awaiting_payment_stage(application)
        current_stage = getattr(application, "current_stage", None)
        current_name = str(getattr(current_stage, "name", "") or "").strip().lower()
        if awaiting_stage and (
            application.current_stage_id != awaiting_stage.id
            and ("approved" in current_name or "payment" in current_name)
        ):
            application.current_stage = awaiting_stage
            update_fields.append("current_stage")
        if getattr(application, "is_approved", False):
            application.is_approved = False
            update_fields.append("is_approved")

    if update_fields:
        application.save(update_fields=list(dict.fromkeys(update_fields)))

    return paid


def _serialize_renewal_application(obj: LicenseApplication):
    data = dict(LicenseApplicationSerializer(obj).data)
    old_license = None
    if getattr(obj, "old_license_id", None):
        old_license = License.objects.filter(license_id=str(obj.old_license_id)).first()

    source_app = None
    if old_license is not None:
        source_app = _resolve_new_license_application_from_license(old_license)
    if source_app is None:
        try:
            source_app = obj.source_object
        except Exception:
            source_app = None

    if source_app is not None:
        try:
            model_name = source_app.__class__.__name__.lower()
            if model_name == "salesmanbarmanmodel":
                from models.transactional.salesman_barman.serializers import SalesmanBarmanSerializer
                source_data = dict(SalesmanBarmanSerializer(source_app).data)
            else:
                from models.transactional.new_license_application.serializers import NewLicenseApplicationSerializer
                source_data = dict(NewLicenseApplicationSerializer(source_app).data)

            orig_security_paid = source_data.get("is_security_fee_paid", False)
            source_data.update(data)
            if model_name != "salesmanbarmanmodel":
                source_data["is_security_fee_paid"] = orig_security_paid or data.get("is_security_fee_paid", False)
            data = source_data
        except Exception:
            pass

    if old_license is not None:
        data.update(
            {
                "old_license_id": old_license.license_id,
                "license_id_display": old_license.license_id,
                "old_license_issue_date": old_license.issue_date,
                "old_license_valid_up_to": old_license.valid_up_to,
                "valid_up_to": old_license.valid_up_to,
                "expired_date": old_license.valid_up_to,
            }
        )
        if getattr(old_license, "source_type", None) == "salesman_barman":
            try:
                from models.transactional.salesman_barman.views import _get_salesman_barman_registration_fee
                sb_fee = _get_salesman_barman_registration_fee()
            except Exception:
                sb_fee = None
            if sb_fee is not None:
                data.update({
                    "license_fee_amount": sb_fee,
                    "licenseFeeAmount": sb_fee,
                    "yearly_license_fee": sb_fee,
                    "yearlyLicenseFee": sb_fee,
                    "security_fee_amount": 0,
                    "securityFeeAmount": 0,
                })
    data["application_id"] = obj.application_id
    data["submitted_on"] = obj.created_at
    data["current_stage_name"] = getattr(getattr(obj, "current_stage", None), "name", None)
    return data


def _pick_renewal_target_stage(application, mode: str) -> WorkflowStage | None:
    transitions = list(WorkflowService.get_next_stages(application).select_related("to_stage"))
    if not transitions:
        return None

    mode = str(mode or "").strip().lower()
    paid = _renewal_is_paid(application)

    def _action(transition):
        condition = getattr(transition, "condition", {}) or {}
        if not isinstance(condition, dict):
            return ""
        return str(condition.get("action", "") or "").strip().upper()

    def _name(transition):
        return str(getattr(getattr(transition, "to_stage", None), "name", "") or "").strip().lower()

    def _has_special_condition(transition):
        condition = getattr(transition, "condition", {}) or {}
        if not isinstance(condition, dict):
            return False
        return (
            condition.get("is_reverted") is True
            or condition.get("isReverted") is True
            or condition.get("objections_resolved") is True
            or condition.get("objectionsResolved") is True
        )

    if mode == "reject":
        for transition in transitions:
            if _action(transition) == "REJECT" or "reject" in _name(transition):
                return transition.to_stage
        return None

    if not paid:
        for transition in transitions:
            if _action(transition) == "PAY" or "payment" in _name(transition):
                return transition.to_stage

    for transition in transitions:
        if _action(transition) in {"APPROVE", "FORWARD"}:
            return transition.to_stage

    for transition in transitions:
        name = _name(transition)
        if "approved" in name or "payment" in name:
            return transition.to_stage

    for transition in transitions:
        name = _name(transition)
        if "reject" not in name and "objection" not in name and not _has_special_condition(transition):
            return transition.to_stage

    return transitions[0].to_stage


def _check_pending_salesman_barman_for_shop_renewal(shop_license):
    if not shop_license or getattr(shop_license, "source_type", None) == "salesman_barman":
        return None

    from models.transactional.salesman_barman.models import SalesmanBarmanModel
    from models.transactional.license_renewal_application.models import LicenseApplication
    from django.contrib.contenttypes.models import ContentType
    from models.masters.license.models import License
    from models.transactional.salesman_barman.payment_status import get_awaiting_payment_stage

    # 1. Check for new salesman/barman applications pending payment
    pending_sb = SalesmanBarmanModel.objects.filter(
        license=shop_license,
        is_print_fee_paid=False
    ).first()
    if pending_sb:
        awaiting_stage = get_awaiting_payment_stage(pending_sb)
        if awaiting_stage and pending_sb.current_stage_id == awaiting_stage.id:
            return f"Please pay the salesman/barman registration fee first for {pending_sb.application_id}, then only you can pay for the license renewal application."
        else:
            return f"Please wait for the approval of the salesman/barman application {pending_sb.application_id} and pay its registration fee first, then only you can pay for the license renewal application."

    # 2. Check for renewed salesman/barman applications pending payment
    sb_apps = SalesmanBarmanModel.objects.filter(license=shop_license)
    sb_ct = ContentType.objects.get_for_model(SalesmanBarmanModel)
    sb_licenses = License.objects.filter(
        source_content_type=sb_ct,
        source_object_id__in=sb_apps.values_list('application_id', flat=True)
    )
    pending_sb_renewals = LicenseApplication.objects.filter(
        old_license_id__in=sb_licenses.values_list('license_id', flat=True),
        is_license_fee_paid=False
    ).first()
    if pending_sb_renewals:
        awaiting_stage = _renewal_awaiting_payment_stage(pending_sb_renewals)
        if awaiting_stage and pending_sb_renewals.current_stage_id == awaiting_stage.id:
            return f"Please pay the salesman/barman renewal fee first for {pending_sb_renewals.application_id}, then only you can pay for the license renewal application."
        else:
            return f"Please wait for the approval of the salesman/barman renewal application {pending_sb_renewals.application_id} and pay its renewal fee first, then only you can pay for the license renewal application."

    return None


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@parser_classes([JSONParser, FormParser, MultiPartParser])
def pay_license_fee_wallet(request, application_id):
    """
    Renewal payment: license fee. After success:
    - licenses.valid_up_to extended based on LICENSE_RENEWAL_TIMER
    - licenses.is_active=True
    - source NewLicenseApplication.is_license_fee_paid=True (when applicable)
    """
    app = get_object_or_404(LicenseApplication, application_id=str(application_id))
    _require_licensee_user(request)
    if app.applicant_id != request.user.id:
        return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

    stage_name = str(getattr(getattr(app, "current_stage", None), "name", "") or "").strip().lower()
    if stage_name and "awaiting payment" not in stage_name and "payment" not in stage_name:
        return Response({"detail": "Payment is not allowed at the current stage."}, status=status.HTTP_400_BAD_REQUEST)

    old_license = get_object_or_404(License, license_id=str(app.old_license_id))

    err = _check_pending_salesman_barman_for_shop_renewal(old_license)
    if err:
        return Response({"detail": err}, status=status.HTTP_400_BAD_REQUEST)

    # Resolve fee from underlying application when available.
    amount = None
    src_app = _resolve_new_license_application_from_license(old_license)
    if src_app is not None:
        try:
            from models.transactional.new_license_application.views import _resolve_license_fee_row, _get_additional_charge_total

            fee = _resolve_license_fee_row(src_app)
            if fee and getattr(fee, "license_fee", None) is not None:
                amount = getattr(fee, "license_fee")
                amount = amount + _get_additional_charge_total(src_app)
        except Exception:
            amount = None
    else:
        if getattr(old_license, "source_type", None) == "salesman_barman":
            try:
                from models.transactional.salesman_barman.views import _get_salesman_barman_registration_fee
                amount = _get_salesman_barman_registration_fee()
            except Exception:
                amount = None

    if amount is None:
        return Response({"detail": "License fee structure not configured for this renewal."}, status=status.HTTP_400_BAD_REQUEST)

    # Resolve wallet licensee id
    wallet_licensee_id = str(old_license.license_id)
    if getattr(old_license, "source_type", None) == "salesman_barman":
        sb_app = getattr(old_license, "source_application", None)
        nli_license_id = None
        if sb_app:
            nli_app = getattr(sb_app, "new_license_application", None)
            if nli_app:
                try:
                    from django.contrib.contenttypes.models import ContentType as CT
                    from models.masters.license.models import License as Lic
                    from models.transactional.new_license_application.models import NewLicenseApplication as NLI
                    nli_ct = CT.objects.get_for_model(NLI)
                    nli_lic = (
                        Lic.objects.filter(
                            source_type="new_license_application",
                            source_content_type=nli_ct,
                            source_object_id=str(nli_app.pk),
                        )
                        .order_by("-issue_date", "-license_id")
                        .first()
                    )
                    if nli_lic:
                        nli_license_id = str(nli_lic.license_id).strip()
                except Exception:
                    pass
        wallet_licensee_id = nli_license_id or str(getattr(request.user, "username", "") or "").strip()

    license_fee_hoa = _resolve_hoa_code(module_type="other", wallet_type="license_fee")
    txn_id = secrets.token_hex(12).upper()
    try:
        debit_wallet_balance(
            transaction_id=txn_id,
            licensee_id=wallet_licensee_id,
            wallet_type="license_fee",
            head_of_account=license_fee_hoa,
            amount=Decimal(str(amount)),
            user_id=str(getattr(request.user, "username", "") or "").strip(),
            remarks=f"Renewal license fee paid for {app.application_id}",
            reference_no=app.application_id,
        )
    except Exception as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    # Mark fee as paid on the renewal tracking application itself
    app.is_license_fee_paid = True
    app.save(update_fields=["is_license_fee_paid"])

    # Flip fee-paid flags on source application (if it was toggled to False after expiry).
    if src_app is not None and not getattr(src_app, "is_license_fee_paid", False):
        try:
            src_app.is_license_fee_paid = True
            src_app.save(update_fields=["is_license_fee_paid"])
        except Exception:
            pass

    _extend_license_validity(old_license)
    try:
        _sync_license_active_from_renewal_payment(old_license, app)
    except Exception:
        pass

    try:
        _sync_renewal_payment_status(app)
    except Exception:
        pass

    return Response({"success": True, "transaction_id": txn_id, "license_id": old_license.license_id})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@parser_classes([JSONParser, FormParser, MultiPartParser])
def pay_security_fee_wallet(request, application_id):
    return Response(
        {"detail": "Security deposit is paid only once during the initial new license application. You do not need to pay it again for renewal."},
        status=status.HTTP_400_BAD_REQUEST
    )




@api_view(["POST"])
@permission_classes([IsAuthenticated])
def approve_renewal_application(request, application_id):
    app = get_object_or_404(LicenseApplication, application_id=str(application_id))
    target_stage = _pick_renewal_target_stage(app, "approve")
    if not target_stage:
        return Response({"detail": "No valid target stage found for approval."}, status=status.HTTP_400_BAD_REQUEST)

    remarks = str(request.data.get("remarks") or "").strip() or "Approved"
    try:
        WorkflowService.advance_stage(
            application=app,
            user=request.user,
            target_stage=target_stage,
            context={"action": "APPROVE", **(request.data.get("context_data") or {})},
            remarks=remarks,
        )
        app.refresh_from_db()
        return Response(_serialize_renewal_application(app), status=status.HTTP_200_OK)
    except Exception as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def reject_renewal_application(request, application_id):
    app = get_object_or_404(LicenseApplication, application_id=str(application_id))
    target_stage = _pick_renewal_target_stage(app, "reject")
    if not target_stage:
        return Response({"detail": "No valid target stage found for rejection."}, status=status.HTTP_400_BAD_REQUEST)

    remarks = str(request.data.get("remarks") or "").strip()
    if not remarks:
        return Response({"detail": "Remarks are required when rejecting a renewal application."}, status=status.HTTP_400_BAD_REQUEST)

    try:
        WorkflowService.reject_application(
            application=app,
            user=request.user,
            target_stage=target_stage,
            remarks=remarks,
        )
        app.refresh_from_db()
        return Response(_serialize_renewal_application(app), status=status.HTTP_200_OK)
    except Exception as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def list_license_applications(request):
    qs = LicenseApplication.objects.all()
    if not getattr(request.user, "is_staff", False) and not getattr(request.user, "is_superuser", False):
        qs = qs.filter(applicant=request.user)
    data = [_serialize_renewal_application(obj) for obj in qs.order_by("-application_id")]
    return Response(data, status=status.HTTP_200_OK)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def license_application_detail(request, pk):
    obj = get_object_or_404(LicenseApplication, application_id=str(pk))
    return Response(_serialize_renewal_application(obj), status=status.HTTP_200_OK)


@permission_classes([IsAuthenticated])
@api_view(["GET"])
def dashboard_counts(request):
    try:
        from models.masters.license.views import deactivate_all_expired_licenses
        deactivate_all_expired_licenses()
    except Exception:
        pass

    wf = _get_renewal_workflow()
    if not wf:
        return Response({"applied": 0, "pending": 0, "objection": 0, "approved": 0, "rejected": 0})

    role = _normalize_role(request.user.role.name if request.user.role else None)
    stage_sets = _get_stage_sets(wf.id)
    all_qs = LicenseApplication.objects.filter(workflow_id=wf.id)

    applied_stages = set(stage_sets["initial"])
    objection_stages = set(stage_sets["objection"])
    approved_stages = set(stage_sets["approved"])
    rejected_stages = set(stage_sets["rejected"])
    payment_stages = set(stage_sets["payment"])
    pending_stages = set(stage_sets["all"]) - applied_stages - approved_stages - rejected_stages - objection_stages - payment_stages

    if role == "licensee":
        base_qs = all_qs.filter(applicant=request.user)
        return Response(
            {
                "applied": base_qs.filter(current_stage__name__in=applied_stages).count(),
                "pending": base_qs.filter(current_stage__name__in=pending_stages).count(),
                "objection": base_qs.filter(current_stage__name__in=objection_stages).count(),
                "approved": base_qs.filter(current_stage__name__in=approved_stages).count(),
                "rejected": base_qs.filter(current_stage__name__in=rejected_stages).count(),
                "awaiting_payment": base_qs.filter(current_stage__name__in=payment_stages).count(),
            }
        )

    role_stage_names = _renewal_role_stage_names(request.user, wf.id)
    if not role_stage_names:
        return Response({"applied": 0, "pending": 0, "objection": 0, "approved": 0, "rejected": 0})

    visible_qs = _renewal_queryset_visible_to_role(all_qs, request.user, role_stage_names)
    pending_for_role = set(role_stage_names)
    return Response(
        {
            "applied": 0,
            "pending": visible_qs.filter(current_stage__name__in=pending_for_role).count(),
            "objection": visible_qs.filter(current_stage__name__in=objection_stages).count(),
            "approved": visible_qs.exclude(
                current_stage__name__in=pending_for_role | objection_stages | rejected_stages
            ).count(),
            "rejected": visible_qs.filter(current_stage__name__in=rejected_stages).count(),
        }
    )


@permission_classes([IsAuthenticated])
@api_view(["GET"])
def application_group(request):
    wf = _get_renewal_workflow()
    if not wf:
        return Response({"applied": [], "pending": [], "objection": [], "approved": [], "rejected": []})

    role = _normalize_role(request.user.role.name if request.user.role else None)
    stage_sets = _get_stage_sets(wf.id)
    all_qs = LicenseApplication.objects.filter(workflow_id=wf.id).select_related("current_stage", "workflow")

    applied_stages = set(stage_sets["initial"])
    objection_stages = set(stage_sets["objection"])
    approved_stages = set(stage_sets["approved"])
    rejected_stages = set(stage_sets["rejected"])
    pending_stages = set(stage_sets["all"]) - applied_stages - approved_stages - rejected_stages - objection_stages

    if role == "licensee":
        base_qs = all_qs.filter(applicant=request.user)
        return Response(
            {
                "applied": LicenseApplicationSerializer(
                    base_qs.filter(current_stage__name__in=applied_stages), many=True
                ).data,
                "pending": LicenseApplicationSerializer(
                    base_qs.filter(current_stage__name__in=pending_stages), many=True
                ).data,
                "objection": LicenseApplicationSerializer(
                    base_qs.filter(current_stage__name__in=objection_stages), many=True
                ).data,
                "approved": LicenseApplicationSerializer(
                    base_qs.filter(current_stage__name__in=approved_stages), many=True
                ).data,
                "rejected": LicenseApplicationSerializer(
                    base_qs.filter(current_stage__name__in=rejected_stages), many=True
                ).data,
            }
        )

    role_stage_names = _renewal_role_stage_names(request.user, wf.id)
    if not role_stage_names:
        return Response({"applied": [], "pending": [], "objection": [], "approved": [], "rejected": []})

    visible_qs = _renewal_queryset_visible_to_role(all_qs, request.user, role_stage_names)
    pending_for_role = set(role_stage_names)
    return Response(
        {
            "applied": [],
            "pending": LicenseApplicationSerializer(
                visible_qs.filter(current_stage__name__in=pending_for_role), many=True
            ).data,
            "objection": LicenseApplicationSerializer(
                visible_qs.filter(current_stage__name__in=objection_stages), many=True
            ).data,
            "approved": LicenseApplicationSerializer(
                visible_qs.exclude(current_stage__name__in=pending_for_role | objection_stages | rejected_stages), many=True
            ).data,
            "rejected": LicenseApplicationSerializer(
                visible_qs.filter(current_stage__name__in=rejected_stages), many=True
            ).data,
        }
    )
