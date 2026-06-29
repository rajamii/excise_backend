from django.db import transaction
from django.shortcuts import get_object_or_404
from django.http import FileResponse, HttpResponse
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.response import Response
from rest_framework import status
from django.utils import timezone
from auth.roles.permissions import HasAppPermission
from auth.workflow.permissions import HasStagePermission
from auth.workflow.models import Workflow, WorkflowStage, WorkflowTransition
from auth.workflow.models import Transaction as WorkflowTransaction
from auth.workflow.constants import WORKFLOW_IDS
from auth.workflow.services import WorkflowService
from models.masters.license.models import License, LicenseValidationToken
from models.masters.core.models import SupplyChainTimerConfig
from .models import SalesmanBarmanModel
from .serializers import SalesmanBarmanSerializer
import re
import secrets
import base64
import hashlib
import mimetypes
from io import BytesIO
from urllib.parse import quote
from django.core import signing
from PIL import Image
from utils.qrcodegen import QrCode
from models.transactional.wallet.wallet_initializer import _resolve_hoa_code
from rest_framework.permissions import IsAuthenticated
from django.core.exceptions import PermissionDenied
from django.contrib.contenttypes.models import ContentType
from models.transactional.payment_gateway.models import MasterPaymentModule
from models.transactional.wallet.wallet_service import debit_wallet_balance


def _normalize_role(role_name):
    if not role_name:
        return None
    normalized = str(role_name).strip().lower().replace('-', '_').replace(' ', '_')
    aliases = {
        'license_user': 'licensee',
        'licensee_user': 'licensee',
        'singlewindow': 'single_window',
        'siteadmin': 'site_admin',
    }
    return aliases.get(normalized, normalized)


def _extract_level_index(stage_name):
    if not stage_name:
        return None
    match = re.match(r'^level_(\d+)$', str(stage_name).strip().lower())
    return int(match.group(1)) if match else None


def _get_stage_sets(workflow_id: int):
    stages = WorkflowStage.objects.filter(workflow_id=workflow_id)
    stage_names = set(stages.values_list('name', flat=True))
    level_stage_names = sorted(
        [name for name in stage_names if _extract_level_index(name) is not None],
        key=lambda name: _extract_level_index(name) or 0
    )
    level_indexes = {name: _extract_level_index(name) for name in level_stage_names}
    objection_stage_names = {name for name in stage_names if 'objection' in str(name).lower()}
    rejected_stage_names = {name for name in stage_names if 'rejected' in str(name).lower()}
    approved_stage_names = {
        stage.name for stage in stages
        if stage.is_final and 'rejected' not in stage.name.lower()
    }
    approved_stage_names.update({name for name in stage_names if 'approved' in str(name).lower()})
    payment_stage_names = {name for name in stage_names if 'payment' in str(name).lower()}
    initial_stage_names = set(stages.filter(is_initial=True).values_list('name', flat=True))

    return {
        'all': stage_names,
        'level': set(level_stage_names),
        'level_ordered': level_stage_names,
        'level_indexes': level_indexes,
        'objection': objection_stage_names,
        'rejected': rejected_stage_names,
        'approved': approved_stage_names,
        'payment': payment_stage_names,
        'initial': initial_stage_names,
    }


def _get_in_progress_stage_names(stage_sets: dict):
    # Any non-final processing stage should be treated as in-progress/pending.
    return set(stage_sets['all']) - set(stage_sets['approved']) - set(stage_sets['rejected'])


def _get_role_stage_names(user, workflow_id: int):
    role = getattr(user, 'role', None)
    if not role:
        return set()
    return set(
        WorkflowStage.objects.filter(
            workflow_id=workflow_id,
            stagepermission__role=role,
            stagepermission__can_process=True
        ).values_list('name', flat=True).distinct()
    )


def _build_role_transition_buckets(user, workflow_id: int, stage_sets: dict):
    role = getattr(user, 'role', None)
    if not role:
        return None

    role_stages = WorkflowStage.objects.filter(
        workflow_id=workflow_id,
        stagepermission__role=role,
        stagepermission__can_process=True
    ).distinct()

    role_stage_ids = set(role_stages.values_list('id', flat=True))
    role_stage_names = set(role_stages.values_list('name', flat=True))
    if not role_stage_ids:
        return None

    transitions = WorkflowTransition.objects.filter(
        workflow_id=workflow_id,
        from_stage_id__in=role_stage_ids
    ).select_related('to_stage')

    approved_targets = set()
    rejected_targets = set()
    objection_targets = set()

    for t in transitions:
        to_name = str(t.to_stage.name or '')
        to_name_lower = to_name.lower()
        condition = t.condition or {}
        action = str(condition.get('action') or '').strip().upper()

        if action == 'REJECT' or 'reject' in to_name_lower:
            rejected_targets.add(to_name)
            continue

        if action in {'RAISE_OBJECTION', 'OBJECTION'} or 'objection' in to_name_lower:
            objection_targets.add(to_name)
            continue

        approved_targets.add(to_name)

    pending_names = set(role_stage_names)
    approved_names = set(approved_targets) | set(stage_sets['approved']) | set(stage_sets['payment'])
    rejected_names = set(rejected_targets) | set(stage_sets['rejected'])
    objection_names = set(objection_targets) | set(stage_sets['objection'])

    return {
        'pending': pending_names,
        'approved': approved_names,
        'rejected': rejected_names,
        'objection': objection_names,
    }

def _create_application(request, workflow_id: int, serializer_cls):
    
    serializer = serializer_cls(data=request.data)
    if not serializer.is_valid():
        print("Validation errors:", serializer.errors)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    with transaction.atomic():
        
        # 1. Workflow & initial stage
        workflow = get_object_or_404(Workflow, id=workflow_id)
        try:
            initial_stage = workflow.stages.get(is_initial=True)
        except WorkflowStage.DoesNotExist:
            return Response(
                {"detail": "Workflow has no initial stage (is_initial=True)."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        district_code = serializer.validated_data['excise_district'].district_code
        prefix = f"SBM/{district_code}/{SalesmanBarmanModel.generate_fin_year()}"
        last_app = SalesmanBarmanModel.objects.filter(
            application_id__startswith=prefix
        ).select_for_update().order_by('-application_id').first()

        last_number = int(last_app.application_id.split('/')[-1]) if last_app else 0
        new_number = str(last_number + 1).zfill(4)
        new_application_id = f"{prefix}/{new_number}"

        
        application = serializer.save(
            workflow=workflow,
            current_stage=initial_stage,
            application_id=new_application_id,
            applicant=request.user
        )

        # 3. Generic workflow submission and auto-forward
        WorkflowService.submit_application(
            application=application,
            user=request.user,
            remarks="Application submitted",
        )

        # 4. Return the *fresh* object (includes generic relations)
        fresh = SalesmanBarmanModel.objects.get(pk=application.pk)
        fresh_serializer = serializer_cls(fresh)
        return Response(fresh_serializer.data, status=status.HTTP_201_CREATED)


def _require_licensee_user(request):
    role = _normalize_role(getattr(getattr(request.user, "role", None), "name", None))
    if role != "licensee":
        raise PermissionDenied("Only licensee can pay from wallet.")


def _resolve_sb_license_for_application(application: SalesmanBarmanModel) -> License | None:
    try:
        ct = ContentType.objects.get_for_model(SalesmanBarmanModel)
        return (
            License.objects.filter(
                source_type="salesman_barman",
                source_content_type=ct,
                source_object_id=str(application.pk),
            )
            .order_by("-issue_date", "-license_id")
            .first()
        )
    except Exception:
        return None


def _fmt_dt(value) -> str:
    if not value:
        return ""
    if hasattr(value, "date") and not hasattr(value, "strftime"):
        value = value.date()
    if hasattr(value, "date") and hasattr(value, "hour"):
        value = value.date()
    return value.strftime("%d/%m/%Y") if hasattr(value, "strftime") else ""


def _fmt_dt_time(value) -> str:
    if not value:
        return ""
    return timezone.localtime(value).strftime("%d/%m/%Y %I:%M %p") if hasattr(value, "tzinfo") else _fmt_dt(value)


def _full_name(application: SalesmanBarmanModel) -> str:
    return " ".join(
        p for p in [
            str(getattr(application, "firstName", "") or "").strip(),
            str(getattr(application, "middleName", "") or "").strip(),
            str(getattr(application, "lastName", "") or "").strip(),
        ] if p
    )


def _build_sb_address(application: SalesmanBarmanModel) -> str:
    parts = []
    if getattr(application, "address", None):
        parts.append(str(application.address).strip())
    license_obj = getattr(application, "license", None)
    source_app = getattr(license_obj, "source_application", None) if license_obj else None
    if source_app:
        for attr in ("location_name", "business_address"):
            value = getattr(source_app, attr, None)
            if value:
                parts.append(str(value).strip())
        if getattr(source_app, "police_station", None) and getattr(source_app.police_station, "police_station", None):
            parts.append(f"P.S - {source_app.police_station.police_station}")
        if getattr(source_app, "ward_name", None):
            parts.append(f"Ward: {source_app.ward_name}")
    return ", ".join(dict.fromkeys([p for p in parts if p]))


def _sb_kind_of_shop(application: SalesmanBarmanModel, issued_license: License | None = None) -> str:
    source_license = issued_license or getattr(application, "license", None)
    category = (
        getattr(getattr(source_license, "license_category", None), "license_category", None)
        or getattr(getattr(application, "license_category", None), "license_category", None)
        or ""
    )
    subcategory = (
        getattr(getattr(source_license, "license_sub_category", None), "description", None)
        or getattr(getattr(getattr(application, "license", None), "license_sub_category", None), "description", None)
        or ""
    )
    parts = [str(category).strip(), str(subcategory).strip()]
    return " - ".join(dict.fromkeys([p for p in parts if p]))


def _make_qr_data_url(payload: str) -> str:
    qr = QrCode.encode_text(str(payload or ""), QrCode.Ecc.MEDIUM)
    size = qr.get_size()
    border = 2
    scale = 4
    img_size = (size + border * 2) * scale
    img = Image.new("RGB", (img_size, img_size), "white")
    pixels = img.load()
    for y in range(size):
        for x in range(size):
            if qr.get_module(x, y):
                for dy in range(scale):
                    for dx in range(scale):
                        pixels[(x + border) * scale + dx, (y + border) * scale + dy] = (0, 0, 0)
    buf = BytesIO()
    img.save(buf, format="PNG")
    return f"data:image/png;base64,{base64.b64encode(buf.getvalue()).decode('ascii')}"


def _ensure_sb_validation_nonce(license_obj: License | None) -> str:
    if not license_obj:
        return ""
    latest = LicenseValidationToken.objects.filter(license=license_obj).order_by("-created_at").first()
    if latest and latest.nonce:
        if str(getattr(license_obj, "validation_nonce", "") or "").strip() != latest.nonce:
            license_obj.validation_nonce = latest.nonce
            license_obj.validation_nonce_updated_at = timezone.now()
            license_obj.save(update_fields=["validation_nonce", "validation_nonce_updated_at"])
        return latest.nonce
    nonce = secrets.token_hex(16)
    license_obj.validation_nonce = nonce
    license_obj.validation_nonce_updated_at = timezone.now()
    license_obj.save(update_fields=["validation_nonce", "validation_nonce_updated_at"])
    return nonce


def _build_sb_validation_link(request, *, application_id: str, nonce: str) -> tuple[str, str, str]:
    signed_code = signing.dumps(
        {"applicationId": application_id, "source": "salesman_barman", "nonce": nonce},
        salt="final-license",
    )
    validation_url = request.build_absolute_uri(f"/v/{quote(signed_code, safe=':')}/")
    verification_id = hashlib.sha256(signed_code.encode("utf-8")).hexdigest()[:12]
    return signed_code, validation_url, verification_id


def _get_sb_validation_payload(request, application: SalesmanBarmanModel, license_obj: License | None):
    if not license_obj:
        return "", "", ""
    latest = LicenseValidationToken.objects.filter(license=license_obj).order_by("-created_at").first()
    if latest and getattr(latest, "signed_code", "") and getattr(latest, "validation_url", ""):
        return str(latest.signed_code), str(latest.validation_url), str(latest.verification_id or "")
    nonce = _ensure_sb_validation_nonce(license_obj)
    signed_code, validation_url, verification_id = _build_sb_validation_link(
        request, application_id=application.application_id, nonce=nonce
    )
    LicenseValidationToken.objects.update_or_create(
        license=license_obj,
        nonce=nonce,
        defaults={
            "signed_code": signed_code,
            "validation_url": validation_url,
            "verification_id": verification_id,
        },
    )
    return signed_code, validation_url, verification_id


def _passport_data_url(passport_file) -> str:
    try:
        if not passport_file or not getattr(passport_file, "name", None) or not passport_file.storage.exists(passport_file.name):
            return ""
        with passport_file.open("rb") as f:
            raw = f.read()
        mime = mimetypes.guess_type(passport_file.name)[0] or "application/octet-stream"
        return f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}"
    except Exception:
        return ""


def _get_salesman_barman_registration_fee() -> float | None:
    from models.masters.core.models import MasterFixedFee
    fee_obj = MasterFixedFee.objects.filter(fee_code="012").only("amount").first()
    if not fee_obj:
        return None
    try:
        return float(getattr(fee_obj, "amount", None))
    except Exception:
        return None


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@parser_classes([JSONParser, FormParser, MultiPartParser])
def pay_registration_fee_wallet(request, application_id):
    """
    Wallet debit for Salesman/Barman Registration fee (module_code=012).
    On success, advance workflow from awaiting_payment -> approved.
    """
    application = get_object_or_404(SalesmanBarmanModel, application_id=application_id)
    _require_licensee_user(request)
    if application.applicant_id != request.user.id:
        return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)



    # Only allow payment once the application is routed to awaiting_payment.
    try:
        from models.transactional.salesman_barman.payment_status import get_awaiting_payment_stage

        awaiting_stage = get_awaiting_payment_stage(application)
        if awaiting_stage and application.current_stage_id != awaiting_stage.id:
            return Response(
                {"detail": "Application is not in payment stage."},
                status=status.HTTP_400_BAD_REQUEST,
            )
    except Exception:
        pass

    amount = _get_salesman_barman_registration_fee()
    if amount is None or amount <= 0:
        return Response(
            {"detail": "Registration fee is not configured for Salesman/Barman (module_code=012)."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # The wallet is keyed by the licensee's NLI license ID (the one recharged via BillDesk),
    # not the SB license ID. Resolve the NLI license ID from the linked NLI application,
    # falling back to the applicant's username so _resolve_wallet_row_licensee_id can find
    # the correct wallet row.
    nli_app = getattr(application, "new_license_application", None)
    nli_license_id = None
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
            amount=amount,
            user_id=str(getattr(request.user, "username", "") or "").strip(),
            remarks=f"Salesman/Barman registration fee paid for {application.application_id}",
            reference_no=application.application_id,
        )
    except Exception as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    # Advance to final approved stage if configured.
    try:
        if not application.is_approved:
            application.is_approved = True
        if hasattr(application, "is_print_fee_paid") and not application.is_print_fee_paid:
            application.is_print_fee_paid = True
        application.save(update_fields=["is_approved", "is_print_fee_paid"])

        approved_stage = (
            application.workflow.stages.filter(name__iexact="approved").order_by("id").first()
            if getattr(application, "workflow_id", None)
            else None
        )
        if approved_stage:
            WorkflowService.advance_stage(
                application=application,
                user=request.user,
                target_stage=approved_stage,
                context={"action": "PAY"},
                remarks="Salesman/Barman registration fee paid via wallet",
            )
            application.refresh_from_db()
    except Exception:
        # Payment succeeded; keep stage as-is if workflow advance fails.
        pass

    return Response({"success": True, "transaction_id": txn_id})


@api_view(['POST'])
@parser_classes([MultiPartParser, FormParser, JSONParser])
@permission_classes([HasStagePermission])
def create_salesman_barman(request):
    return _create_application(request, WORKFLOW_IDS['SALESMAN_BARMAN'], SalesmanBarmanSerializer)


@api_view(['POST'])
@permission_classes([HasStagePermission])
def initiate_renewal(request, license_id):
    """
    Initiate renewal by creating a pre-filled new application from an existing license.
    """
    old_license = get_object_or_404(License, license_id=license_id, source_type='salesman_barman')

    old_app = old_license.source_application
    if not isinstance(old_app, SalesmanBarmanModel):
        return Response({"detail": "Invalid license source."}, status=status.HTTP_400_BAD_REQUEST)

    if old_app.applicant != request.user:
        return Response({"detail": "You can only renew your own license."}, status=status.HTTP_403_FORBIDDEN)

    def get_timer_days(code: str, default_days: int) -> float:
        cfg = (
            SupplyChainTimerConfig.objects.filter(code=code, is_active=True)
            .order_by("-updated_at", "-id")
            .first()
        )
        if not cfg:
            return float(default_days)

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
                return float(value_int)
            if unit in ("week", "wk"):
                return float(value_int * 7)
            if unit in ("month", "mon", "mo"):
                return float(value_int * 30)
            if unit in ("year", "yr"):
                return float(value_int * 365)
            if unit in ("hour", "hr"):
                return float(value_int) / 24.0
            if unit in ("minute", "min"):
                return float(value_int) / (24.0 * 60.0)
            if unit in ("second", "sec"):
                return float(value_int) / (24.0 * 3600.0)

        days = getattr(cfg, "validity_period_days", None)
        if days is not None:
            try:
                return float(max(0, int(days)))
            except (TypeError, ValueError):
                return float(default_days)

        return float(default_days)

    from datetime import timedelta
    now_dt = timezone.now()
    reminder_days = get_timer_days("LICENSE_RENEWAL_REMINDER_TIMER", 90)

    # SOP: Require main license renewal first
    from django.contrib.contenttypes.models import ContentType
    from models.transactional.license_renewal_application.models import LicenseApplication

    sb_ct = ContentType.objects.get_for_model(SalesmanBarmanModel)
    main_licenses = License.objects.filter(
        applicant=request.user,
        source_type__in=['new_license_application', 'license_application']
    )

    for main_lic in main_licenses:
        main_reminder_days = get_timer_days("LICENSE_RENEWAL_REMINDER_TIMER", 90)
        if main_lic.valid_up_to and main_lic.valid_up_to <= now_dt + timedelta(days=main_reminder_days):
            main_renewal_exists = LicenseApplication.objects.filter(
                old_license_id=main_lic.license_id,
            ).exclude(source_content_type=sb_ct).exists()

            if not main_renewal_exists:
                return Response(
                    {"detail": f"Please renew your new license ({main_lic.license_id}) first before renewing Salesman/Barman application."},
                    status=status.HTTP_400_BAD_REQUEST
                )

    # Best-effort: keep license status consistent once it crosses expiry.
    if getattr(old_license, "valid_up_to", None) and old_license.valid_up_to < now_dt and getattr(old_license, "is_active", True):
        old_license.is_active = False
        old_license.save(update_fields=["is_active"])

    # Bypassed early renewal check for testing
    pass
    # if old_license.valid_up_to > now_dt + timedelta(days=reminder_days):
    #     window_start = old_license.valid_up_to - timedelta(days=reminder_days)
    #     window_end = old_license.valid_up_to
    #     return Response({
    #         "detail": (
    #             "Renewal not allowed yet. "
    #             f"You can renew from {window_start.strftime('%d/%m/%Y')} "
    #             f"to {window_end.strftime('%d/%m/%Y')}."
    #         ),
    #         "renewal_window_starts_on": window_start.isoformat(),
    #         "renewal_window_ends_on": window_end.isoformat(),
    #         "license_valid_up_to": old_license.valid_up_to.isoformat(),
    #         "reminder_window_days": reminder_days,
    #     }, status=status.HTTP_400_BAD_REQUEST)

    # Generate application_id manually using RSBM prefix
    district_code = str(old_app.excise_district.district_code)
    from models.transactional.license_renewal_application.models import LicenseApplication
    fin_year = LicenseApplication.generate_fin_year()
    prefix = f"RSBM/{district_code}/{fin_year}"

    with transaction.atomic():
        last = (
            LicenseApplication.objects.filter(
                application_id__startswith=prefix + "/"
            ).select_for_update().order_by('-application_id').first()
        )
        last_number = 0
        if last and "/" in last.application_id:
            try:
                last_number = int(last.application_id.split("/")[-1])
            except Exception:
                last_number = 0
        new_number = str(last_number + 1).zfill(4)
        new_application_id = f"{prefix}/{new_number}"

        # Get workflow and initial stage for renewal
        from models.transactional.license_renewal_application.views import _get_renewal_workflow
        wf = _get_renewal_workflow()
        if not wf:
            return Response({"detail": "Renewal workflow is not configured."}, status=status.HTTP_400_BAD_REQUEST)
        initial_stage = wf.stages.filter(is_initial=True).order_by("id").first()
        if not initial_stage:
            return Response({"detail": "Renewal workflow has no initial stage."}, status=status.HTTP_400_BAD_REQUEST)

        # Check for active renewal
        from models.transactional.helpers import _get_stage_sets
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

        from django.contrib.contenttypes.models import ContentType
        new_application = LicenseApplication.objects.create(
            application_id=new_application_id,
            is_approved=False,
            old_license_id=old_license.license_id,
            applicant=request.user,
            license_category=old_license.license_category,
            license_sub_category=old_license.license_sub_category,
            workflow=wf,
            current_stage=initial_stage,
            source_content_type=ContentType.objects.get_for_model(SalesmanBarmanModel),
            source_object_id=old_app.pk,
        )

    # Log submission transaction
    WorkflowService.submit_application(
        application=new_application,
        user=request.user,
        remarks="Renewal application initiated and submitted successfully (Salesman/Barman)"
    )

    # Return serialized renewal application data
    from models.transactional.license_renewal_application.views import _serialize_renewal_application
    return Response({
        "detail": "Renewal application initiated and submitted successfully.",
        "application": _serialize_renewal_application(new_application)
    }, status=status.HTTP_201_CREATED)


@permission_classes([HasAppPermission('salesman_barman_registration', 'view'), HasStagePermission])
@api_view(['GET'])
def list_salesman_barman(request):
    role = _normalize_role(request.user.role.name if request.user.role else None)

    if role in ["site_admin"]:
        applications = SalesmanBarmanModel.objects.all()
    elif role == "licensee":
        applications = SalesmanBarmanModel.objects.filter(applicant=request.user)
    else:
        applications = SalesmanBarmanModel.objects.filter(
            current_stage__stagepermission__role=request.user.role,
            current_stage__stagepermission__can_process=True
        ).distinct()

    serializer = SalesmanBarmanSerializer(applications, many=True)
    return Response(serializer.data)


@permission_classes([HasAppPermission('salesman_barman_registration', 'view')])
@api_view(['GET'])
def salesman_barman_detail(request, application_id):
    app = get_object_or_404(SalesmanBarmanModel, application_id=application_id)
    serializer = SalesmanBarmanSerializer(app)
    response = Response(serializer.data)
    response["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response["Pragma"] = "no-cache"
    response["Expires"] = "0"
    return response


@permission_classes([HasAppPermission('salesman_barman_registration', 'view')])
@api_view(['GET'])
def final_license_detail(request, application_id):
    raw_id = str(application_id or "").strip()
    token = raw_id
    low = token.lower()
    if low.startswith("val:") or low.startswith("val-") or low.startswith("val "):
        token = token[4:].strip()

    resolved_application_id = raw_id
    validated_via_code = False
    try:
        payload = signing.loads(token, salt="final-license")
        if isinstance(payload, dict) and payload.get("source") == "salesman_barman" and payload.get("applicationId"):
            resolved_application_id = str(payload["applicationId"])
            validated_via_code = True
    except Exception:
        resolved_application_id = raw_id

    application = get_object_or_404(SalesmanBarmanModel, application_id=resolved_application_id)
    role = _normalize_role(request.user.role.name if request.user.role else None)
    if role == "licensee" and application.applicant_id != request.user.id:
        return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

    license_obj = _resolve_sb_license_for_application(application)
    validation_code, validation_url, _verification_id = _get_sb_validation_payload(request, application, license_obj)
    passport_file = getattr(application, "passPhoto", None)
    passport_exists = False
    passport_url = ""
    try:
        passport_exists = bool(passport_file and getattr(passport_file, "name", None) and passport_file.storage.exists(passport_file.name))
        if passport_exists and hasattr(passport_file, "url"):
            passport_url = request.build_absolute_uri(passport_file.url)
    except Exception:
        passport_exists = False

    role_label = str(getattr(application, "role", "") or "Salesman").strip().title()
    license_number = license_obj.license_id if license_obj else application.application_id
    district = getattr(getattr(application, "excise_district", None), "district", "") or ""

    renewal_application_id = None
    try:
        from models.transactional.license_renewal_application.models import LicenseApplication

        ct = ContentType.objects.get_for_model(application)
        renewal = LicenseApplication.objects.filter(source_content_type=ct, source_object_id=application.pk).order_by('-created_at').first()
        if renewal:
            renewal_application_id = renewal.application_id
    except Exception:
        pass

    response = {
        "applicationId": application.application_id,
        "renewalApplicationId": renewal_application_id,
        "renewal_application_id": renewal_application_id,
        "certificateType": "salesman-barman",
        "licenseNumber": license_number,
        "licenseTitle": f"{role_label} Registration Certificate",
        "validationCode": validation_code,
        "validationPdfUrl": validation_url,
        "validatedViaCode": validated_via_code,
        "print_count": int(getattr(license_obj, "print_count", 0) or getattr(application, "print_count", 0) or 0),
        "is_print_fee_paid": bool(getattr(license_obj, "is_print_fee_paid", False) or getattr(application, "is_print_fee_paid", False)),
        "terms": [],
        "licenseeName": _full_name(application),
        "fatherOrHusbandName": str(getattr(application, "fatherHusbandName", "") or ""),
        "kindOfShop": _sb_kind_of_shop(application, license_obj),
        "addressOfBusiness": _build_sb_address(application),
        "district": district,
        "modeOfOperation": role_label,
        "passportPhotoUrl": passport_url,
        "passportPhotoExists": passport_exists,
        "passportPhotoDataUrl": _passport_data_url(passport_file),
        "licenseFee": "",
        "transactionRef": "",
        "transactionDate": "",
        "validFrom": _fmt_dt(getattr(license_obj, "issue_date", None)),
        "validTo": _fmt_dt(getattr(license_obj, "valid_up_to", None)),
        "generatedOn": _fmt_dt(timezone.now().date()),
        "applicationDateTime": _fmt_dt_time(getattr(application, "created_at", None)),
        "qrCodeDataUrl": _make_qr_data_url(validation_url),
    }

    return Response(response, status=status.HTTP_200_OK)


@permission_classes([HasAppPermission('salesman_barman_registration', 'view')])
@api_view(['GET'])
def final_license_passport_photo(request, application_id):
    application = get_object_or_404(SalesmanBarmanModel, application_id=application_id)
    role = _normalize_role(request.user.role.name if request.user.role else None)
    if role == "licensee" and application.applicant_id != request.user.id:
        return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

    passport_file = getattr(application, "passPhoto", None)
    try:
        if not passport_file or not getattr(passport_file, "name", None) or not passport_file.storage.exists(passport_file.name):
            return Response({"detail": "Photo not available."}, status=status.HTTP_404_NOT_FOUND)
        f = passport_file.open("rb")
    except Exception:
        return Response({"detail": "Photo not available."}, status=status.HTTP_404_NOT_FOUND)

    mime = mimetypes.guess_type(passport_file.name)[0] or "application/octet-stream"
    return FileResponse(f, content_type=mime)


@permission_classes([HasAppPermission('salesman_barman_registration', 'view')])
@api_view(['GET'])
def final_license_qr_code(request, application_id):
    application = get_object_or_404(SalesmanBarmanModel, application_id=application_id)
    role = _normalize_role(request.user.role.name if request.user.role else None)
    if role == "licensee" and application.applicant_id != request.user.id:
        return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

    license_obj = _resolve_sb_license_for_application(application)
    _validation_code, validation_url, _verification_id = _get_sb_validation_payload(request, application, license_obj)

    data_url = _make_qr_data_url(validation_url)
    b64 = data_url.split(",", 1)[1] if "," in data_url else ""
    return HttpResponse(base64.b64decode(b64), content_type="image/png")


# Dashboard Counts
@permission_classes([HasAppPermission('salesman_barman_registration', 'view'), HasStagePermission])
@api_view(['GET'])
def dashboard_counts(request):
    try:
        from models.masters.license.views import deactivate_all_expired_licenses
        deactivate_all_expired_licenses()
    except Exception:
        pass
    role = _normalize_role(request.user.role.name if request.user.role else None)
    workflow_id = WORKFLOW_IDS['SALESMAN_BARMAN']
    stage_sets = _get_stage_sets(workflow_id)
    all_qs = SalesmanBarmanModel.objects.all()

    month = request.query_params.get('month')
    year = request.query_params.get('year')
    if month:
        all_qs = all_qs.filter(created_at__month=month)
    if year:
        all_qs = all_qs.filter(created_at__year=year)

    if role == 'licensee':
        base_qs = all_qs.filter(applicant=request.user)
        applied_stages = set(stage_sets['initial'])
        objection_stages = set(stage_sets['objection'])
        payment_stages = set(stage_sets['payment'])
        pending_stages = _get_in_progress_stage_names(stage_sets) - applied_stages - objection_stages - payment_stages
        # The licensee UI does not surface an "Applied" tile; treat initial-stage apps as pending.
        pending_for_ui = pending_stages | applied_stages
        return Response({
            "applied": base_qs.filter(current_stage__name__in=applied_stages).count(),
            "pending": base_qs.filter(current_stage__name__in=pending_for_ui).count(),
            "objection": base_qs.filter(current_stage__name__in=objection_stages).count(),
            "approved": base_qs.filter(current_stage__name__in=stage_sets['approved']).count(),
            "rejected": base_qs.filter(current_stage__name__in=stage_sets['rejected']).count(),
            "awaiting_payment": base_qs.filter(current_stage__name__in=payment_stages).count(),
        })

    if role in ['site_admin', 'single_window']:
        applied_stages = set(stage_sets['initial'])
        pending_stages = _get_in_progress_stage_names(stage_sets) - applied_stages
        pending_for_ui = pending_stages | applied_stages
        return Response({
            "applied": all_qs.filter(current_stage__name__in=applied_stages).count(),
            "pending": all_qs.filter(current_stage__name__in=pending_for_ui).count(),
            "approved": all_qs.filter(current_stage__name__in=stage_sets['approved']).count(),
            "rejected": all_qs.filter(current_stage__name__in=stage_sets['rejected']).count(),
        })

    role_stage_names = _get_role_stage_names(request.user, workflow_id)
    if not role_stage_names:
        return Response({
            "pending": 0,
            "approved": 0,
            "rejected": 0,
            "objection": 0,
        })

    from django.db.models import OuterRef, Exists, Q

    content_type = ContentType.objects.get_for_model(SalesmanBarmanModel)
    role_id = getattr(getattr(request.user, 'role', None), 'id', None)
    
    acted_by_role = Exists(
        WorkflowTransaction.objects.filter(
            content_type=content_type, 
            object_id=OuterRef('application_id'),
            performed_by__role_id=role_id
        )
    )

    role_id = getattr(getattr(request.user, 'role', None), 'id', None)
    pending_stages = set(role_stage_names)
    rejected_stages = set(stage_sets['rejected'])
    objection_stages = set(stage_sets['objection'])

    pending_count = all_qs.filter(current_stage__name__in=pending_stages).count()
    approved_count = (
        all_qs.exclude(current_stage__name__in=pending_stages | rejected_stages | objection_stages)
        .annotate(_acted_by_role=acted_by_role)
        .filter(_acted_by_role=True)
        .count()
    )
    rejected_count = (
        all_qs.filter(current_stage__name__in=rejected_stages)
        .annotate(_acted_by_role=acted_by_role)
        .filter(_acted_by_role=True)
        .count()
    )
    objection_count = (
        all_qs.filter(current_stage__name__in=objection_stages)
        .annotate(_acted_by_role=acted_by_role)
        .filter(_acted_by_role=True)
        .count()
    )

    return Response({
        "pending": pending_count,
        "approved": approved_count,
        "rejected": rejected_count,
        "objection": objection_count,
    })

@permission_classes([HasAppPermission('salesman_barman_registration', 'view'), HasStagePermission])
@api_view(['GET'])
@parser_classes([JSONParser])
def application_group(request):
    role = _normalize_role(request.user.role.name if request.user.role else None)
    workflow_id = WORKFLOW_IDS['SALESMAN_BARMAN']
    stage_sets = _get_stage_sets(workflow_id)
    all_qs = SalesmanBarmanModel.objects.all()

    if role == 'licensee':
        base_qs = SalesmanBarmanModel.objects.filter(applicant=request.user)
        applied_stages = set(stage_sets['initial'])
        objection_stages = set(stage_sets['objection'])
        pending_stages = _get_in_progress_stage_names(stage_sets) - applied_stages - objection_stages
        result = {
            "applied": SalesmanBarmanSerializer(
                base_qs.filter(current_stage__name__in=applied_stages),
                many=True
            ).data,
            "pending": SalesmanBarmanSerializer(
                base_qs.filter(current_stage__name__in=pending_stages),
                many=True
            ).data,
            "objection": SalesmanBarmanSerializer(
                base_qs.filter(current_stage__name__in=objection_stages),
                many=True
            ).data,
            "approved": SalesmanBarmanSerializer(
                base_qs.filter(current_stage__name__in=stage_sets['approved']),
                many=True
            ).data,
            "rejected": SalesmanBarmanSerializer(
                base_qs.filter(current_stage__name__in=stage_sets['rejected']),
                many=True
            ).data
        }
        return Response(result)

    if role in ['site_admin']:
        applied_stages = set(stage_sets['initial'])
        pending_stages = _get_in_progress_stage_names(stage_sets) - applied_stages
        return Response({
            "applied": SalesmanBarmanSerializer(
                all_qs.filter(current_stage__name__in=applied_stages), many=True
            ).data,
            "pending": SalesmanBarmanSerializer(
                all_qs.filter(current_stage__name__in=pending_stages), many=True
            ).data,
            "approved": SalesmanBarmanSerializer(
                all_qs.filter(current_stage__name__in=stage_sets['approved']), many=True
            ).data,
            "rejected": SalesmanBarmanSerializer(
                all_qs.filter(current_stage__name__in=stage_sets['rejected']), many=True
            ).data
        })

    role_stage_names = _get_role_stage_names(request.user, workflow_id)
    if role_stage_names:
        from django.db.models import OuterRef, Exists, Q

        content_type = ContentType.objects.get_for_model(SalesmanBarmanModel)
        role_id = getattr(getattr(request.user, 'role', None), 'id', None)
        
        acted_by_role = Exists(
            WorkflowTransaction.objects.filter(
                content_type=content_type, 
                object_id=OuterRef('application_id'),
                performed_by__role_id=role_id
            )
        )

        role_id = getattr(getattr(request.user, 'role', None), 'id', None)
        pending_stages = set(role_stage_names)
        rejected_stages = set(stage_sets['rejected'])
        objection_stages = set(stage_sets['objection'])

        approved_qs = (
            all_qs.exclude(current_stage__name__in=pending_stages | rejected_stages | objection_stages)
            .annotate(_acted_by_role=acted_by_role)
            .filter(_acted_by_role=True)
        )
        rejected_qs = (
            all_qs.filter(current_stage__name__in=rejected_stages)
            .annotate(_acted_by_role=acted_by_role)
            .filter(_acted_by_role=True)
        )
        objection_qs = (
            all_qs.filter(current_stage__name__in=objection_stages)
            .annotate(_acted_by_role=acted_by_role)
            .filter(_acted_by_role=True)
        )

        return Response({
            "pending": SalesmanBarmanSerializer(
                all_qs.filter(current_stage__name__in=pending_stages), many=True
            ).data,
            "approved": SalesmanBarmanSerializer(approved_qs, many=True).data,
            "rejected": SalesmanBarmanSerializer(rejected_qs, many=True).data,
            "objection": SalesmanBarmanSerializer(objection_qs, many=True).data,
        })

    return Response({
        "applied": [],
        "pending": [],
        "approved": [],
        "rejected": [],
        "objection": []
    })
