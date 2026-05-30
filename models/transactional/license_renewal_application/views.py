from django.shortcuts import get_object_or_404
from datetime import date, timedelta
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

    days = getattr(cfg, "validity_period_days", None)
    if days is not None:
        try:
            return max(0, int(days))
        except (TypeError, ValueError):
            return int(default_days)

    unit = str(getattr(cfg, "delay_unit", "") or "").lower().strip()
    value = getattr(cfg, "delay_value", None)
    try:
        value_int = max(0, int(value or 0))
    except (TypeError, ValueError):
        return int(default_days)

    if unit.endswith("s"):
        unit = unit[:-1]
    if unit == "day":
        return value_int
    if unit in ("month", "mon", "mo"):
        return value_int * 30
    if unit in ("hour", "hr"):
        return max(0, value_int // 24)
    return int(default_days)


def _extend_license_validity(lic: License) -> License:
    today = date.today()
    renewal_days = _get_timer_days("LICENSE_RENEWAL_TIMER", 365)
    base = lic.valid_up_to if lic.valid_up_to and lic.valid_up_to > today else today
    lic.valid_up_to = base + timedelta(days=renewal_days)
    lic.is_active = True
    lic.save(update_fields=["valid_up_to", "is_active"])
    return lic


def _resolve_new_license_application_from_license(lic: License):
    if getattr(lic, "source_type", None) != "new_license_application":
        return None
    try:
        return lic.source_application
    except Exception:
        return None


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
            from models.transactional.new_license_application.serializers import NewLicenseApplicationSerializer

            source_data = dict(NewLicenseApplicationSerializer(source_app).data)
            source_data.update(data)
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
    data["application_id"] = obj.application_id
    data["submitted_on"] = obj.created_at
    data["current_stage_name"] = getattr(getattr(obj, "current_stage", None), "name", None)
    return data


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

    # Resolve fee from underlying NewLicenseApplication when available.
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

    if amount is None:
        return Response({"detail": "License fee structure not configured for this renewal."}, status=status.HTTP_400_BAD_REQUEST)

    license_fee_hoa = _resolve_hoa_code(module_type="other", wallet_type="license_fee")
    txn_id = secrets.token_hex(12).upper()
    try:
        debit_wallet_balance(
            transaction_id=txn_id,
            licensee_id=str(old_license.license_id),
            wallet_type="license_fee",
            head_of_account=license_fee_hoa,
            amount=Decimal(str(amount)),
            user_id=str(getattr(request.user, "username", "") or "").strip(),
            remarks=f"Renewal license fee paid for {app.application_id}",
            reference_no=app.application_id,
        )
    except Exception as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    # Flip fee-paid flags on source application (if it was toggled to False after expiry).
    if src_app is not None and not getattr(src_app, "is_license_fee_paid", False):
        try:
            src_app.is_license_fee_paid = True
            src_app.save(update_fields=["is_license_fee_paid"])
        except Exception:
            pass

    _extend_license_validity(old_license)

    return Response({"success": True, "transaction_id": txn_id, "license_id": old_license.license_id})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@parser_classes([JSONParser, FormParser, MultiPartParser])
def pay_security_fee_wallet(request, application_id):
    """
    Renewal payment: security fee. After success:
    - source NewLicenseApplication.is_security_fee_paid=True (when applicable)
    """
    app = get_object_or_404(LicenseApplication, application_id=str(application_id))
    _require_licensee_user(request)
    if app.applicant_id != request.user.id:
        return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

    stage_name = str(getattr(getattr(app, "current_stage", None), "name", "") or "").strip().lower()
    if stage_name and "awaiting payment" not in stage_name and "payment" not in stage_name:
        return Response({"detail": "Payment is not allowed at the current stage."}, status=status.HTTP_400_BAD_REQUEST)

    old_license = get_object_or_404(License, license_id=str(app.old_license_id))

    amount = None
    src_app = _resolve_new_license_application_from_license(old_license)
    if src_app is not None:
        try:
            from models.transactional.new_license_application.views import _resolve_license_fee_row, _get_additional_charge_total

            fee = _resolve_license_fee_row(src_app)
            if fee and getattr(fee, "security_amount", None) is not None:
                amount = getattr(fee, "security_amount")
                amount = amount + _get_additional_charge_total(src_app)
        except Exception:
            amount = None

    if amount is None:
        return Response({"detail": "Security fee structure not configured for this renewal."}, status=status.HTTP_400_BAD_REQUEST)

    security_deposit_hoa = _resolve_hoa_code(module_type="other", wallet_type="security_deposit")
    txn_id = secrets.token_hex(12).upper()
    try:
        debit_wallet_balance(
            transaction_id=txn_id,
            licensee_id=str(old_license.license_id),
            wallet_type="security_deposit",
            head_of_account=security_deposit_hoa,
            amount=Decimal(str(amount)),
            user_id=str(getattr(request.user, "username", "") or "").strip(),
            remarks=f"Renewal security fee paid for {app.application_id}",
            reference_no=app.application_id,
        )
    except Exception as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    if src_app is not None and not getattr(src_app, "is_security_fee_paid", False):
        try:
            src_app.is_security_fee_paid = True
            src_app.save(update_fields=["is_security_fee_paid"])
        except Exception:
            pass

    return Response({"success": True, "transaction_id": txn_id, "license_id": old_license.license_id})


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
    pending_stages = set(stage_sets["all"]) - applied_stages - approved_stages - rejected_stages - objection_stages

    if role == "licensee":
        base_qs = all_qs.filter(applicant=request.user)
        return Response(
            {
                "applied": base_qs.filter(current_stage__name__in=applied_stages).count(),
                "pending": base_qs.filter(current_stage__name__in=pending_stages).count(),
                "objection": base_qs.filter(current_stage__name__in=objection_stages).count(),
                "approved": base_qs.filter(current_stage__name__in=approved_stages).count(),
                "rejected": base_qs.filter(current_stage__name__in=rejected_stages).count(),
            }
        )

    if role in ["site_admin"]:
        return Response(
            {
                "applied": all_qs.filter(current_stage__name__in=applied_stages).count(),
                "pending": all_qs.filter(current_stage__name__in=pending_stages).count(),
                "objection": all_qs.filter(current_stage__name__in=objection_stages).count(),
                "approved": all_qs.filter(current_stage__name__in=approved_stages).count(),
                "rejected": all_qs.filter(current_stage__name__in=rejected_stages).count(),
            }
        )

    role_stage_names = _get_role_stage_names(request.user, wf.id)
    if not role_stage_names:
        return Response({"pending": 0, "approved": 0, "rejected": 0})

    pending_for_role = set(role_stage_names) | objection_stages
    return Response(
        {
            "pending": all_qs.filter(current_stage__name__in=pending_for_role).count(),
            "approved": all_qs.exclude(current_stage__name__in=pending_for_role | rejected_stages).count(),
            "rejected": all_qs.filter(current_stage__name__in=rejected_stages).count(),
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

    if role in ["site_admin"]:
        return Response(
            {
                "applied": LicenseApplicationSerializer(
                    all_qs.filter(current_stage__name__in=applied_stages), many=True
                ).data,
                "pending": LicenseApplicationSerializer(
                    all_qs.filter(current_stage__name__in=pending_stages), many=True
                ).data,
                "objection": LicenseApplicationSerializer(
                    all_qs.filter(current_stage__name__in=objection_stages), many=True
                ).data,
                "approved": LicenseApplicationSerializer(
                    all_qs.filter(current_stage__name__in=approved_stages), many=True
                ).data,
                "rejected": LicenseApplicationSerializer(
                    all_qs.filter(current_stage__name__in=rejected_stages), many=True
                ).data,
            }
        )

    role_stage_names = _get_role_stage_names(request.user, wf.id)
    if not role_stage_names:
        return Response({"applied": [], "pending": [], "objection": [], "approved": [], "rejected": []})

    pending_for_role = set(role_stage_names) | objection_stages
    return Response(
        {
            "applied": [],
            "pending": LicenseApplicationSerializer(
                all_qs.filter(current_stage__name__in=pending_for_role), many=True
            ).data,
            "objection": LicenseApplicationSerializer(
                all_qs.filter(current_stage__name__in=objection_stages), many=True
            ).data,
            "approved": LicenseApplicationSerializer(
                all_qs.exclude(current_stage__name__in=pending_for_role | rejected_stages), many=True
            ).data,
            "rejected": LicenseApplicationSerializer(
                all_qs.filter(current_stage__name__in=rejected_stages), many=True
            ).data,
        }
    )
