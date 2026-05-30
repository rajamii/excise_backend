from django.shortcuts import get_object_or_404
from datetime import date, timedelta
from django.db import transaction
from django.db.models import OuterRef, Subquery, BooleanField, TextField
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from auth.roles.permissions import HasAppPermission
from auth.workflow.permissions import HasStagePermission
from auth.workflow.services import WorkflowService
from auth.workflow.models import Workflow
from auth.workflow.models import Transaction as WorkflowTransaction
from auth.workflow.constants import WORKFLOW_IDS
from .models import NewLicenseApplication
from models.masters.license.models import License, LicenseValidationToken
from .serializers import NewLicenseApplicationSerializer
from auth.workflow.models import WorkflowStage
from models.masters.core.models import Location
from django.core.exceptions import ValidationError, PermissionDenied
from django.utils import timezone
from django.contrib.contenttypes.models import ContentType
from django.http import FileResponse, HttpResponse
from io import BytesIO
import base64
import mimetypes
from PIL import Image
from utils.qrcodegen import QrCode
from models.transactional.wallet.wallet_initializer import _resolve_hoa_code
from models.masters.license.master_license_form import MasterLicenseForm
from models.masters.license.master_license_form_terms import MasterLicenseFormTerms
from models.masters.license.legacy_codes import resolve_codes_for_license_form
from django.core import signing
from urllib.parse import quote
import secrets
import hashlib
from models.transactional.helpers import _normalize_role, _get_stage_sets, _get_role_stage_names
from models.masters.core.models import LicenseFee, SupplyChainTimerConfig
from models.transactional.wallet.wallet_service import debit_wallet_balance
from .payment_status import sync_new_license_payment_status
import logging
import secrets
from decimal import Decimal
from django.conf import settings

logger = logging.getLogger(__name__)
from decimal import Decimal


def _with_application_fee_payment_annotations(qs):
    """
    Annotate NewLicenseApplication queryset with latest BillDesk application-fee payment info.

    - application_fee_payment_status: 'P'/'S'/'F'
    - application_fee_transaction_id: utr
    - application_fee_payment_date: transaction_date
    - application_fee_error: response_errordescription
    """
    try:
        from models.transactional.payment_gateway.models import PaymentBilldeskTransaction

        base = PaymentBilldeskTransaction.objects.filter(
            payer_id__iexact=OuterRef("application_id"),
            payment_module_code="001",
        ).order_by("-transaction_date", "-utr")

        return qs.annotate(
            application_fee_payment_status=Subquery(base.values("payment_status")[:1]),
            application_fee_transaction_id=Subquery(base.values("utr")[:1]),
            application_fee_payment_date=Subquery(base.values("transaction_date")[:1]),
            application_fee_error=Subquery(base.values("response_errordescription")[:1]),
        )
    except Exception:
        return qs


def _with_site_enquiry_revert_annotations(qs):
    """
    Annotate NewLicenseApplication queryset with SiteEnquiryReport revert info.

    - site_enquiry_is_reverted: boolean
    - site_enquiry_reverted_remarks: text
    """
    try:
        from models.transactional.site_enquiry.models import SiteEnquiryReport

        ct = ContentType.objects.get_for_model(NewLicenseApplication)
        base = SiteEnquiryReport.objects.filter(
            content_type=ct,
            object_id=OuterRef("application_id"),
        ).order_by("-updated_at", "-created_at")

        return qs.annotate(
            site_enquiry_is_reverted=Subquery(base.values("is_reverted")[:1], output_field=BooleanField()),
            site_enquiry_reverted_remarks=Subquery(base.values("reverted_remarks")[:1], output_field=TextField()),
        )
    except Exception:
        return qs


def _ensure_license_validation_nonce(license_obj: License | None) -> str:
    if not license_obj:
        return ''

    try:
        latest = LicenseValidationToken.objects.filter(license=license_obj).order_by('-created_at').first()
        if latest and latest.nonce:
            if str(getattr(license_obj, 'validation_nonce', '') or '').strip() != latest.nonce:
                license_obj.validation_nonce = latest.nonce
                license_obj.validation_nonce_updated_at = timezone.now()
                license_obj.save(update_fields=['validation_nonce', 'validation_nonce_updated_at'])
            return latest.nonce
    except Exception:
        pass

    nonce = secrets.token_hex(16)
    try:
        LicenseValidationToken.objects.create(license=license_obj, nonce=nonce)
    except Exception:
        nonce = secrets.token_hex(16)
        LicenseValidationToken.objects.create(license=license_obj, nonce=nonce)

    license_obj.validation_nonce = nonce
    license_obj.validation_nonce_updated_at = timezone.now()
    license_obj.save(update_fields=['validation_nonce', 'validation_nonce_updated_at'])
    return nonce


def _build_validation_link(request, *, application_id: str, source: str, nonce: str) -> tuple[str, str, str]:
    signing_payload = {"applicationId": application_id, "source": source, "nonce": nonce}
    signed_code = signing.dumps(signing_payload, salt="final-license")
    validation_url = request.build_absolute_uri(f"/v/{quote(signed_code, safe=':')}/")
    verification_id = hashlib.sha256(signed_code.encode("utf-8")).hexdigest()[:12]
    return signed_code, validation_url, verification_id




def _create_salesman_barman_record(application, user):
    """
    Create (or update) the linked SalesmanBarmanModel record after the NLI transaction
    has committed. Must be called OUTSIDE the NLI atomic block to avoid nested
    transaction.atomic() calls in generate_application_id() aborting the outer transaction.
    """
    mode = getattr(application, "mode_of_operation", None)
    if mode not in {"Salesman", "Barman"}:
        return

    member_payload = getattr(application, "_member_payload", {}) or {}

    try:
        from models.transactional.salesman_barman.models import SalesmanBarmanModel
        from auth.workflow.constants import WORKFLOW_IDS as _WF_IDS
        from auth.workflow.models import WorkflowStage, Workflow

        wf = Workflow.objects.filter(id=_WF_IDS.get("SALESMAN_BARMAN")).first()
        if not wf:
            import logging
            logging.getLogger(__name__).warning("SALESMAN_BARMAN workflow (id=%s) not found.", _WF_IDS.get("SALESMAN_BARMAN"))
            return

        init = WorkflowStage.objects.filter(workflow=wf, is_initial=True).order_by("id").first()
        if not init:
            import logging
            logging.getLogger(__name__).warning("No initial stage for SALESMAN_BARMAN workflow.")
            return

        sb = (
            SalesmanBarmanModel.objects
            .filter(new_license_application=application)
            .first()
        )
        if not sb:
            sb = SalesmanBarmanModel(
                workflow=wf,
                current_stage=init,
                new_license_application=application,
                excise_district=getattr(application, "site_district", None),
                license_category=getattr(application, "license_category", None),
                license=None,
                applicant=user,
                role=mode,
            )

        # Parse member name into parts
        name = (member_payload.get("member_name") or "").strip()
        parts = [p for p in name.split(" ") if p]
        first_name = parts[0] if parts else None
        last_name = parts[-1] if len(parts) > 1 else (parts[0] if parts else None)
        middle_name = " ".join(parts[1:-1]) if len(parts) > 2 else None

        sb.role = mode
        if first_name:
            sb.firstName = first_name
        if middle_name is not None:
            sb.middleName = middle_name
        if last_name:
            sb.lastName = last_name

        father_husband_name = member_payload.get("member_father_husband_name") or getattr(application, "father_husband_name", None)
        if father_husband_name:
            sb.fatherHusbandName = father_husband_name

        gender = member_payload.get("member_gender") or getattr(application, "gender", None)
        if gender:
            sb.gender = gender

        dob = member_payload.get("member_dob") or getattr(application, "dob", None)
        if dob is not None:
            sb.dob = dob

        nationality = member_payload.get("member_nationality") or getattr(application, "nationality", None)
        if nationality:
            sb.nationality = nationality

        address = (member_payload.get("member_address") or
                   getattr(application, "present_address", None) or
                   getattr(application, "permanent_address", None))
        if address:
            sb.address = address

        pan = member_payload.get("member_pan") or getattr(application, "pan", None)
        if pan:
            sb.pan = pan

        if member_payload.get("aadhaar"):
            sb.aadhaar = member_payload["aadhaar"]
        if member_payload.get("member_mobile_number"):
            sb.mobileNumber = member_payload["member_mobile_number"]
        if member_payload.get("member_email"):
            sb.emailId = member_payload["member_email"]
        if member_payload.get("sikkim_subject") is not None:
            sb.sikkimSubject = member_payload["sikkim_subject"]
        if member_payload.get("member_pass_photo") is not None:
            sb.passPhoto = member_payload["member_pass_photo"]
        if member_payload.get("member_aadhaar_card") is not None:
            sb.aadhaarCard = member_payload["member_aadhaar_card"]
        if member_payload.get("member_residential_certificate") is not None:
            sb.residentialCertificate = member_payload["member_residential_certificate"]
        if member_payload.get("member_dob_proof") is not None:
            sb.dateofBirthProof = member_payload["member_dob_proof"]

        if user and not getattr(sb, "applicant_id", None):
            sb.applicant = user
        if getattr(application, "site_district_id", None):
            sb.excise_district = application.site_district
        if getattr(application, "license_category_id", None):
            sb.license_category = application.license_category

        sb.save()

    except Exception:
        import traceback
        traceback.print_exc()
        # Do not re-raise — SB failure must never block the NLI response.


def _create_application(request, workflow_id: int, serializer_cls, *, auto_submit: bool = True):

    serializer = serializer_cls(data=request.data, context={"request": request})
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    try:
        workflow = get_object_or_404(Workflow, id=workflow_id)

        try:
            initial_stage = workflow.stages.get(is_initial=True)
        except WorkflowStage.DoesNotExist:
            return Response(
                {"detail": "Workflow has no initial stage (is_initial=True)."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            district_code = serializer.validated_data['site_district'].district_code
            prefix = f"NLI/{district_code}/{NewLicenseApplication.generate_fin_year()}"
            last_app = NewLicenseApplication.objects.filter(
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

            if auto_submit:
                WorkflowService.submit_application(
                    application=application,
                    user=request.user,
                    remarks="Application submitted"
                )

        # Transaction committed — refresh from DB to pick up auto_now fields and any
        # changes made by the model's save() (e.g. licensee_fee_id).
        application.refresh_from_db()

        # Create the linked SalesmanBarmanModel record AFTER the NLI transaction has
        # committed and in its own separate transaction. This avoids nested atomic()
        # calls inside generate_application_id() aborting the outer NLI transaction.
        _create_salesman_barman_record(application, request.user)

        fresh_serializer = serializer_cls(application)
        return Response(fresh_serializer.data, status=status.HTTP_201_CREATED)

    except ValidationError as e:
        return Response(
            {"detail": str(e.message) if hasattr(e, 'message') else str(e)},
            status=status.HTTP_400_BAD_REQUEST
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        return Response(
            {"detail": f"Submission failed: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@parser_classes([MultiPartParser, FormParser, JSONParser])
@permission_classes([HasStagePermission])
def create_new_license_application(request):
    # Do not submit/forward the workflow on click; submission happens only after BillDesk success callback.
    return _create_application(request, WORKFLOW_IDS['LICENSE_APPROVAL'], NewLicenseApplicationSerializer, auto_submit=False)


@api_view(['POST'])
@parser_classes([MultiPartParser, FormParser, JSONParser])
@permission_classes([HasStagePermission])
def create_new_license_application_draft(request):
    """
    Create a new license application record without submitting the workflow.

    Used for BillDesk application-fee (module_code=001) flows where the application
    is auto-submitted only after a successful gateway callback.
    """
    return _create_application(request, WORKFLOW_IDS['LICENSE_APPROVAL'], NewLicenseApplicationSerializer, auto_submit=False)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def force_submit_new_license_application(request, application_id):
    """
    DEV/LOCALHOST ONLY: Force-submit a new license application by simulating a successful
    application-fee payment (BillDesk module_code=001).

    This exists to enable local testing where the payment gateway cannot be used.
    """
    allow = bool(getattr(settings, "DEBUG", False) or getattr(settings, "BILLDESK_USE_MOCK", False))
    if not allow:
        return Response({"detail": "Force submit is disabled in this environment."}, status=status.HTTP_403_FORBIDDEN)

    role = _normalize_role(request.user.role.name if getattr(request.user, "role", None) else None)
    if role != "licensee":
        return Response({"detail": "Only licensees can force submit."}, status=status.HTTP_403_FORBIDDEN)

    app_id = str(application_id or "").strip()
    app = (
        NewLicenseApplication.objects.select_related("workflow", "current_stage", "applicant")
        .filter(application_id__iexact=app_id)
        .first()
    )
    if not app or getattr(app, "applicant_id", None) != getattr(request.user, "id", None):
        return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

    # Resolve module fee from master payment module (001). Non-blocking if missing.
    module_fee = Decimal("0.00")
    try:
        from models.transactional.payment_gateway.models import MasterPaymentModule, PaymentBilldeskTransaction

        mm = MasterPaymentModule.objects.filter(module_code="001", visibility_status=True).first()
        if mm and mm.license_fee is not None:
            module_fee = Decimal(str(mm.license_fee)).quantize(Decimal("0.01"))

        # Create a synthetic successful payment transaction so annotation queries can show status.
        utr = f"FORCE-NLI-{secrets.token_hex(8).upper()}"
        PaymentBilldeskTransaction.objects.create(
            utr=utr,
            transaction_id_no_hoa=utr,
            payer_id=str(app.application_id),
            payment_module_code="001",
            transaction_amount=module_fee,
            payment_status="S",
            user_id=str(getattr(request.user, "username", "") or "").strip()[:50] or None,
        )
    except Exception as exc:
        logger.warning("Force-submit: failed to record synthetic payment transaction for %s: %s", app.application_id, exc)

    # Persist application-fee payment status on the application row.
    try:
        if not getattr(app, "is_application_fee_paid", False):
            app.is_application_fee_paid = True
            app.save(update_fields=["is_application_fee_paid"])
    except Exception:
        pass

    # Restore to initial stage if it was previously pushed into a rejected/final stage.
    try:
        stage = getattr(app, "current_stage", None)
        stage_name = str(getattr(stage, "name", "") or "").strip().lower()
        is_rejected_or_final = bool((stage_name and "reject" in stage_name) or bool(getattr(stage, "is_final", False)))
        if is_rejected_or_final and getattr(app, "workflow", None):
            initial = app.workflow.stages.filter(is_initial=True).order_by("id").first()
            if initial and getattr(app, "current_stage_id", None) != getattr(initial, "id", None):
                app.current_stage = initial
                app.save(update_fields=["current_stage"])
    except Exception:
        pass

    # Submit the workflow if still at the initial stage.
    try:
        if getattr(getattr(app, "current_stage", None), "is_initial", False):
            WorkflowService.submit_application(
                application=app,
                user=request.user,
                remarks="Force submitted (localhost/dev): application fee bypassed",
            )
    except Exception as exc:
        logger.exception("Force-submit: WorkflowService.submit_application failed for %s: %s", app.application_id, exc)
        return Response({"detail": f"Force submit failed: {exc}"}, status=status.HTTP_400_BAD_REQUEST)

    # Try auto-submit the salesman/barman linked workflow (best effort).
    sbm_submitted = False
    sbm_application_id = ""
    sbm_submit_error = ""
    try:
        if getattr(app, "mode_of_operation", None) in {"Salesman", "Barman"}:
            from models.transactional.salesman_barman.models import SalesmanBarmanModel
            from auth.workflow.constants import WORKFLOW_IDS as _WF_IDS
            from auth.workflow.models import WorkflowStage as _WFStage, Workflow as _WF
            from django.db import transaction as db_transaction

            wf = _WF.objects.filter(id=_WF_IDS.get("SALESMAN_BARMAN")).first()
            if not wf:
                raise ValueError(f"SALESMAN_BARMAN workflow (id={_WF_IDS.get('SALESMAN_BARMAN')}) not found in DB.")

            init = _WFStage.objects.filter(workflow=wf, is_initial=True).order_by("id").first()
            if not init:
                raise ValueError("No initial stage found for SALESMAN_BARMAN workflow.")

            sb = (
                SalesmanBarmanModel.objects.select_related("workflow", "current_stage", "applicant")
                .filter(new_license_application=app)
                .first()
            )
            if not sb:
                sb = SalesmanBarmanModel(
                    workflow=wf,
                    current_stage=init,
                    new_license_application=app,
                    excise_district=getattr(app, "site_district", None),
                    license_category=getattr(app, "license_category", None),
                    license=None,
                    applicant=request.user,
                    role=getattr(app, "mode_of_operation", None),
                )
            else:
                if not getattr(sb, "workflow_id", None):
                    sb.workflow = wf
                if not getattr(sb, "current_stage_id", None):
                    sb.current_stage = init
                if getattr(app, "site_district_id", None):
                    sb.excise_district = app.site_district
                if getattr(app, "license_category_id", None):
                    sb.license_category = app.license_category
                if getattr(app, "mode_of_operation", None) in {"Salesman", "Barman"}:
                    sb.role = app.mode_of_operation

            with db_transaction.atomic():
                sb.save()

            sbm_application_id = str(getattr(sb, "application_id", "") or "").strip()
            sb.refresh_from_db()
            if getattr(getattr(sb, "current_stage", None), "is_initial", False):
                WorkflowService.submit_application(
                    application=sb,
                    user=request.user,
                    remarks="Auto-submitted with New License Application (force submit)",
                )
                sbm_submitted = True
    except Exception as exc:
        logger.warning("Force-submit: SBM auto-submit failed for %s: %s", app.application_id, exc)
        sbm_submit_error = str(exc)

    serializer = NewLicenseApplicationSerializer(app)
    return Response(
        {
            "application_id": app.application_id,
            "forced": True,
            "is_application_fee_paid": True,
            "sbm_submitted": sbm_submitted,
            "sbm_application_id": sbm_application_id,
            "sbm_submit_error": sbm_submit_error,
            "application": serializer.data,
        },
        status=status.HTTP_200_OK,
    )


@api_view(['POST'])
@permission_classes([HasStagePermission])
def initiate_renewal(request, license_id):
    """
    Initiate renewal by creating a pre-filled new application from an existing license.
    """
    old_license = get_object_or_404(License, license_id=license_id, source_type='new_license_application')

    old_app = old_license.source_application
    if not isinstance(old_app, NewLicenseApplication):
        return Response({"detail": "Invalid license source."}, status=status.HTTP_400_BAD_REQUEST)

    if old_app.applicant != request.user:
        return Response({"detail": "You can only renew your own license."}, status=status.HTTP_403_FORBIDDEN)

    def get_timer_days(code: str, default_days: int) -> int:
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

    today = date.today()
    reminder_days = get_timer_days("LICENSE_RENEWAL_REMINDER_TIMER", 90)
    if old_license.valid_up_to > today + timedelta(days=reminder_days):
        return Response({
            "detail": f"Renewal not allowed yet. License valid until {old_license.valid_up_to.strftime('%d/%m/%Y')}. "
                     f"You can renew within the last {reminder_days} days or after expiry."
        }, status=status.HTTP_400_BAD_REQUEST)

    # Build pre-filled data
    new_data = {
        'license_type': old_app.license_type,
        'license_category': old_app.license_category,
        'license_sub_category': old_app.license_sub_category,
        'establishment_name': old_app.establishment_name,
        'site_type': old_app.site_type,
        'applicant_name': old_app.applicant_name,
        'father_husband_name': old_app.father_husband_name,
        'dob': old_app.dob,
        'gender': old_app.gender,
        'nationality': old_app.nationality,
        'residential_status': old_app.residential_status,
        'present_address': old_app.present_address,
        'permanent_address': old_app.permanent_address,
        'pan': old_app.pan,
        'email': old_app.email,
        'mobile_number': old_app.mobile_number,
        'mode_of_operation': old_app.mode_of_operation,
        'site_district': old_app.site_district,
        'site_subdivision': old_app.site_subdivision,
        'road_name': old_app.road_name,
        'ward_name': old_app.ward_name,
        'police_station': old_app.police_station,
        'pin_code': old_app.pin_code,
        'company_name': old_app.company_name,
        'company_pan': old_app.company_pan,
        'company_cin': old_app.company_cin,
        'company_email': old_app.company_email,
        'company_phone_number': old_app.company_phone_number,
        # Documents (carry forward for renewal)
        'pass_photo': old_app.pass_photo,
        'pan_card': old_app.pan_card,
        'sikkim_certificate': old_app.sikkim_certificate,
        'dob_proof': old_app.dob_proof,
        'noc_landlord': old_app.noc_landlord,
    }

    # Manual creation
    district_code = str(old_app.site_district.district_code)
    fin_year = NewLicenseApplication.generate_fin_year()
    prefix = f"NLI/{district_code}/{fin_year}"

    with transaction.atomic():
        last_app = NewLicenseApplication.objects.filter(
            application_id__startswith=prefix
        ).select_for_update().order_by('-application_id').first()

        last_number = int(last_app.application_id.split('/')[-1]) if last_app else 0
        new_number = str(last_number + 1).zfill(4)
        new_application_id = f"{prefix}/{new_number}"

        workflow = get_object_or_404(Workflow, id=WORKFLOW_IDS['LICENSE_APPROVAL'])
        initial_stage = workflow.stages.get(is_initial=True)

        new_application = NewLicenseApplication.objects.create(
            application_id=new_application_id,
            workflow=workflow,
            current_stage=initial_stage,
            applicant=request.user,
            renewal_of=old_license,
            **new_data,
        )

    WorkflowService.submit_application(
        application=new_application,
        user=request.user,
        remarks="Renewal application auto-submitted"
    )

    serializer = NewLicenseApplicationSerializer(new_application)
    return Response({
        "detail": "Renewal application initiated and submitted successfully.",
        "application": serializer.data
    }, status=status.HTTP_201_CREATED)


@permission_classes([HasAppPermission('new_license_application', 'view'), HasStagePermission])
@api_view(['GET'])
def list_license_applications(request):
    role = _normalize_role(request.user.role.name if request.user.role else None)

    if role in ["site_admin"]:
        applications = NewLicenseApplication.objects.all()
    elif role == "licensee":
        applications = NewLicenseApplication.objects.filter(applicant=request.user)
    else:
        applications = NewLicenseApplication.objects.filter(
            current_stage__stagepermission__role=request.user.role,
            current_stage__stagepermission__can_process=True
        ).distinct()

    applications = _with_application_fee_payment_annotations(applications)
    serializer = NewLicenseApplicationSerializer(applications, many=True)
    return Response(serializer.data)


# License Application Detail
@permission_classes([HasAppPermission('new_license_application', 'view')])
@api_view(['GET'])
def license_application_detail(request, pk):
    raw_pk = str(pk or "").strip()
    if raw_pk.isdigit():
        application = get_object_or_404(NewLicenseApplication, pk=int(raw_pk))
    else:
        application = get_object_or_404(NewLicenseApplication, application_id=raw_pk)

    role = _normalize_role(request.user.role.name if request.user.role else None)
    if role == "licensee" and application.applicant_id != request.user.id:
        return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

    # Attach latest application-fee payment info for details view too.
    application = _with_application_fee_payment_annotations(NewLicenseApplication.objects.filter(pk=application.pk)).first() or application
    serializer = NewLicenseApplicationSerializer(application)
    return Response(serializer.data)


# Final License Detail (for printing/viewing in UI)
@permission_classes([HasAppPermission('new_license_application', 'view')])
@api_view(['GET'])
def final_license_detail(request, application_id):
    raw_id = str(application_id or "").strip()
    token = raw_id
    low = token.lower()
    if low.startswith("val:"):
        token = token[4:].strip()
    elif low.startswith("val-"):
        token = token[4:].strip()
    elif low.startswith("val "):
        token = token[4:].strip()

    resolved_application_id = raw_id
    validated_via_code = False
    try:
        payload = signing.loads(token, salt="final-license")
        if isinstance(payload, dict) and payload.get("source") == "new_license_application" and payload.get("applicationId"):
            resolved_application_id = str(payload["applicationId"])
            validated_via_code = True
    except Exception:
        resolved_application_id = raw_id

    application = get_object_or_404(NewLicenseApplication, application_id=resolved_application_id)

    role = _normalize_role(request.user.role.name if request.user.role else None)
    if role == "licensee" and application.applicant_id != request.user.id:
        return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

    new_app_ct = ContentType.objects.get_for_model(NewLicenseApplication)
    license_obj = License.objects.filter(
        source_type="new_license_application",
        source_content_type=new_app_ct,
        source_object_id=application.application_id,
    ).order_by("-issue_date").first()

    def fmt_dt(d):
        return d.strftime("%d/%m/%Y") if d else ""

    def build_address():
        parts = []
        if getattr(application, "location_name", None):
            parts.append(str(application.location_name).strip())
        if getattr(application, "ward_name", None):
            parts.append(f"Ward: {str(application.ward_name).strip()}")
        if getattr(application, "business_address", None):
            parts.append(str(application.business_address).strip())
        if getattr(application, "police_station", None):
            parts.append(f"P.S - {application.police_station.police_station}")
        if getattr(application, "site_subdivision", None):
            parts.append(f"Sub Division - {application.site_subdivision.subdivision}")
        if getattr(application, "pin_code", None):
            parts.append(f"Pin - {application.pin_code}")
        return ", ".join([p for p in parts if p])

    def _pick_passport_file():
        candidates = [getattr(application, "pass_photo", None)]
        if getattr(application, "renewal_of", None) and getattr(application.renewal_of, "source_application", None):
            src = application.renewal_of.source_application
            candidates.append(getattr(src, "pass_photo", None))
        for c in candidates:
            try:
                if c and getattr(c, "name", None) and c.storage.exists(c.name):
                    return c
            except Exception:
                continue
        return None

    photo_url = ""
    photo_exists = False
    passport_photo_data_url = ""
    passport_file = _pick_passport_file()
    if passport_file and hasattr(passport_file, "url"):
        try:
            photo_url = request.build_absolute_uri(passport_file.url)
        except Exception:
            photo_url = ""

        photo_exists = True
        try:
            with passport_file.open("rb") as f:
                raw = f.read()
            mime = mimetypes.guess_type(passport_file.name)[0] or "application/octet-stream"
            b64 = base64.b64encode(raw).decode("ascii")
            passport_photo_data_url = f"data:{mime};base64,{b64}"
        except Exception:
            passport_photo_data_url = ""

    def make_qr_data_url(payload: str) -> str:
        qr = QrCode.encode_text(str(payload), QrCode.Ecc.MEDIUM)
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
                            px = (x + border) * scale + dx
                            py = (y + border) * scale + dy
                            pixels[px, py] = (0, 0, 0)

        buf = BytesIO()
        img.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        return f"data:image/png;base64,{b64}"

    validation_code = ""
    validation_url = ""
    if license_obj:
        latest_token = LicenseValidationToken.objects.filter(license=license_obj).order_by("-created_at").first()
        if latest_token and getattr(latest_token, "signed_code", "") and getattr(latest_token, "validation_url", ""):
            validation_code = str(latest_token.signed_code)
            validation_url = str(latest_token.validation_url)
        else:
            nonce = _ensure_license_validation_nonce(license_obj)
            if nonce:
                signed_code, full_url, verification_id = _build_validation_link(
                    request, application_id=application.application_id, source="new_license_application", nonce=nonce
                )
                LicenseValidationToken.objects.update_or_create(
                    license=license_obj,
                    nonce=nonce,
                    defaults={
                        "signed_code": signed_code,
                        "validation_url": full_url,
                        "verification_id": verification_id,
                    },
                )
                validation_code = signed_code
                validation_url = full_url

    response = {
        "applicationId": application.application_id,
        "licenseNumber": (license_obj.license_id if license_obj else application.application_id),
        "licenseTitle": "",
        "validationCode": validation_code,
        "validationPdfUrl": validation_url,
        "validatedViaCode": validated_via_code,
        "print_count": int(getattr(license_obj, "print_count", 0) or 0) if license_obj else 0,
        "is_print_fee_paid": bool(getattr(license_obj, "is_print_fee_paid", False)) if license_obj else False,
        "terms": [],
        # Debug/compat fields: the (legacy) codes used to pick terms/title.
        # Frontend can ignore these safely.
        "termsCatCode": None,
        "termsScatCode": None,
        "licenseeName": application.applicant_name,
        "fatherOrHusbandName": application.father_husband_name,
        "kindOfShop": application.license_type.license_type if application.license_type else "",
        "addressOfBusiness": build_address(),
        "district": application.site_district.district if application.site_district else "",
        "modeOfOperation": application.get_mode_of_operation_display() if hasattr(application, "get_mode_of_operation_display") else application.mode_of_operation,
        "passportPhotoUrl": photo_url,
        "passportPhotoExists": photo_exists,
        "passportPhotoDataUrl": passport_photo_data_url,
        "licenseFee": "",
        "transactionRef": "",
        "transactionDate": "",
        "validFrom": fmt_dt(license_obj.issue_date) if license_obj else fmt_dt(application.created_at.date()),
        "validTo": fmt_dt(license_obj.valid_up_to) if license_obj else "",
        "generatedOn": fmt_dt(timezone.now().date()),
        "qrCodeDataUrl": make_qr_data_url(validation_url),
    }

    try:
        fee_id = getattr(application, "licensee_fee_id", None)
        if fee_id:
            fee = LicenseFee.objects.filter(id=int(fee_id), is_active=True).first()
            if fee:
                response["licenseFee"] = str(getattr(fee, "license_fee", "") or "")
    except Exception:
        pass

    cat_code = getattr(license_obj, "license_category_id", None) if license_obj else None
    scat_code = getattr(license_obj, "license_sub_category_id", None) if license_obj else None
    if cat_code is None:
        cat_code = getattr(application, "license_category_id", None)
    if scat_code is None:
        scat_code = getattr(application, "license_sub_category_id", None)
    if cat_code is not None and scat_code is not None:
        resolved_cat, resolved_scat = resolve_codes_for_license_form(int(cat_code), int(scat_code))
        response["termsCatCode"] = resolved_cat
        response["termsScatCode"] = resolved_scat
        cfg = MasterLicenseForm.get_license_config(int(resolved_cat), int(resolved_scat)) if resolved_cat is not None and resolved_scat is not None else None
        if cfg:
            response["licenseTitle"] = cfg.license_title

        qs = (
            MasterLicenseFormTerms.objects.filter(
                licensee_cat_code=int(resolved_cat),
                licensee_scat_code=int(resolved_scat),
            ).order_by("sl_no")
            if resolved_cat is not None and resolved_scat is not None
            else MasterLicenseFormTerms.objects.none()
        )
        terms = [str(t.license_terms).strip() for t in qs if getattr(t, "license_terms", None)]
        terms = [t for t in terms if t]
        response["terms"] = terms

    return Response(response, status=status.HTTP_200_OK)


@permission_classes([HasAppPermission('new_license_application', 'view')])
@api_view(['GET'])
def final_license_passport_photo(request, application_id):
    application = get_object_or_404(NewLicenseApplication, application_id=application_id)

    role = _normalize_role(request.user.role.name if request.user.role else None)
    if role == "licensee" and application.applicant_id != request.user.id:
        return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

    def _pick_passport_file():
        candidates = [getattr(application, "pass_photo", None)]
        if getattr(application, "renewal_of", None) and getattr(application.renewal_of, "source_application", None):
            src = application.renewal_of.source_application
            candidates.append(getattr(src, "pass_photo", None))
        for c in candidates:
            try:
                if c and getattr(c, "name", None) and c.storage.exists(c.name):
                    return c
            except Exception:
                continue
        return None

    passport_file = _pick_passport_file()
    if not passport_file:
        return Response({"detail": "Photo not available."}, status=status.HTTP_404_NOT_FOUND)

    try:
        f = passport_file.open("rb")
    except Exception:
        return Response({"detail": "Photo not available."}, status=status.HTTP_404_NOT_FOUND)

    mime = mimetypes.guess_type(passport_file.name)[0] or "application/octet-stream"
    return FileResponse(f, content_type=mime)


@permission_classes([HasAppPermission('new_license_application', 'view')])
@api_view(['GET'])
def final_license_qr_code(request, application_id):
    application = get_object_or_404(NewLicenseApplication, application_id=application_id)

    role = _normalize_role(request.user.role.name if request.user.role else None)
    if role == "licensee" and application.applicant_id != request.user.id:
        return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

    new_app_ct = ContentType.objects.get_for_model(NewLicenseApplication)
    license_obj = License.objects.filter(
        source_type="new_license_application",
        source_content_type=new_app_ct,
        source_object_id=application.application_id,
    ).order_by("-issue_date").first()

    if license_obj:
        try:
            latest_token = LicenseValidationToken.objects.filter(license=license_obj).order_by('-created_at').first()
            if latest_token and latest_token.nonce:
                if str(getattr(license_obj, 'validation_nonce', '') or '').strip() != latest_token.nonce:
                    license_obj.validation_nonce = latest_token.nonce
                    license_obj.validation_nonce_updated_at = timezone.now()
                    license_obj.save(update_fields=['validation_nonce', 'validation_nonce_updated_at'])
        except Exception:
            pass

    payload = ""
    if license_obj:
        latest_token = LicenseValidationToken.objects.filter(license=license_obj).order_by("-created_at").first()
        if latest_token and getattr(latest_token, "validation_url", ""):
            payload = str(latest_token.validation_url)
        else:
            nonce = _ensure_license_validation_nonce(license_obj)
            if nonce:
                signed_code, full_url, verification_id = _build_validation_link(
                    request, application_id=application.application_id, source="new_license_application", nonce=nonce
                )
                LicenseValidationToken.objects.update_or_create(
                    license=license_obj,
                    nonce=nonce,
                    defaults={
                        "signed_code": signed_code,
                        "validation_url": full_url,
                        "verification_id": verification_id,
                    },
                )
                payload = full_url

    qr = QrCode.encode_text(str(payload), QrCode.Ecc.MEDIUM)
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
                        px = (x + border) * scale + dx
                        py = (y + border) * scale + dy
                        pixels[px, py] = (0, 0, 0)

    buf = BytesIO()
    img.save(buf, format="PNG")
    return HttpResponse(buf.getvalue(), content_type="image/png")


# Print License View
@permission_classes([HasAppPermission('new_license_application', 'update')])
@api_view(['POST'])
@parser_classes([JSONParser])
def print_license_view(request, application_id):
    license = get_object_or_404(NewLicenseApplication, application_id=application_id)

    new_app_ct = ContentType.objects.get_for_model(NewLicenseApplication)
    license_obj = License.objects.filter(
        source_type="new_license_application",
        source_content_type=new_app_ct,
        source_object_id=license.application_id,
    ).order_by("-issue_date").first()

    # Some datasets have License issued but `is_approved` not synced on the application row.
    # If a License exists, allow printing and token rotation.
    if not license_obj:
        return Response({"error": "License is not issued yet."}, status=403)
    if not license_obj.is_active:
        return Response({"error": "License fee and security fee must be paid before printing."}, status=403)

    can_print, fee = license_obj.can_print_license()

    if not can_print:
        return Response({
            "error": "Print limit exceeded. Please pay ₹500 to continue printing.",
            "fee_required": fee
        }, status=403)

    if fee > 0 and not license_obj.is_print_fee_paid:
        return Response({"error": "₹500 fee not paid yet."}, status=403)

    license_obj.record_license_print(fee_paid=(fee > 0))

    if license_obj:
        nonce = secrets.token_hex(16)
        signed_code, full_url, verification_id = _build_validation_link(
            request, application_id=license.application_id, source="new_license_application", nonce=nonce
        )
        try:
            LicenseValidationToken.objects.create(
                license=license_obj,
                nonce=nonce,
                signed_code=signed_code,
                validation_url=full_url,
                verification_id=verification_id,
            )
        except Exception:
            nonce = secrets.token_hex(16)
            signed_code, full_url, verification_id = _build_validation_link(
                request, application_id=license.application_id, source="new_license_application", nonce=nonce
            )
            LicenseValidationToken.objects.create(
                license=license_obj,
                nonce=nonce,
                signed_code=signed_code,
                validation_url=full_url,
                verification_id=verification_id,
            )

        license_obj.validation_nonce = nonce
        license_obj.validation_nonce_updated_at = timezone.now()
        license_obj.save(update_fields=['validation_nonce', 'validation_nonce_updated_at'])

        validation_code = signed_code
        validation_url = full_url
    else:
        validation_code = ""
        validation_url = ""

    return Response({
        "success": "License printed.",
        "print_count": license_obj.print_count,
        "validationCode": validation_code,
        "validationPdfUrl": validation_url,
    })


def _require_licensee_user(request):
    if not getattr(request.user, "is_authenticated", False):
        raise PermissionDenied("Authentication required.")
    role = _normalize_role(request.user.role.name if getattr(request.user, "role", None) else None)
    if role != "licensee":
        raise PermissionDenied("Only licensees can pay fees.")


def _resolve_na_license_for_application(application: NewLicenseApplication) -> License | None:
    new_app_ct = ContentType.objects.get_for_model(NewLicenseApplication)
    return (
        License.objects.filter(
            source_type="new_license_application",
            source_content_type=new_app_ct,
            source_object_id=application.application_id,
        )
        .order_by("-issue_date", "-license_id")
        .first()
    )


def _resolve_license_fee_row(application: NewLicenseApplication) -> LicenseFee | None:
    fee_id = getattr(application, "licensee_fee_id", None)
    try:
        if fee_id:
            fee = LicenseFee.objects.filter(id=int(fee_id), is_active=True).first()
            if fee:
                return fee
    except Exception:
        pass

    # Fallback: resolve fee row from category/subcategory (+ location when available).
    # This matches serializer behavior and prevents "fee structure not configured"
    # when `licensee_fee_id` hasn't been persisted yet.
    try:
        cat_id = getattr(application, "license_category_id", None)
        scat_id = getattr(application, "license_sub_category_id", None)
        if not cat_id or not scat_id:
            return None

        district_code = None
        try:
            district_code = getattr(getattr(application, "site_district", None), "district_code", None)
        except Exception:
            district_code = None

        location_code = None
        if district_code is not None:
            location = (
                Location.objects.filter(district_code=district_code, is_active=True)
                .order_by("location_code")
                .first()
            )
            location_code = getattr(location, "location_code", None) if location else None

        qs = LicenseFee.objects.filter(is_active=True)

        direct = qs.filter(
            license_category_id=int(cat_id),
            license_subcategory_id=int(scat_id),
        )
        if location_code is not None:
            direct = direct.filter(location_code_id=int(location_code))
        fee = direct.order_by("id").first()
        if fee:
            return fee

        # Try again without location constraint (fee rows may have null location_code).
        fee = qs.filter(
            license_category_id=int(cat_id),
            license_subcategory_id=int(scat_id),
        ).order_by("id").first()
        if fee:
            return fee

        category = getattr(application, "license_category", None)
        subcategory = getattr(application, "license_sub_category", None)
        cat_code = getattr(category, "old_license_cat_code", None)
        scat_code = getattr(subcategory, "old_license_scat_code", None)
        if cat_code is None or scat_code is None:
            return None

        legacy = qs.filter(
            license_category__old_license_cat_code=int(cat_code),
            license_subcategory__old_license_scat_code=int(scat_code),
        )
        if location_code is not None:
            legacy = legacy.filter(location_code_id=int(location_code))
        fee = legacy.order_by("id").first()
        if fee:
            return fee

        return qs.filter(
            license_category__old_license_cat_code=int(cat_code),
            license_subcategory__old_license_scat_code=int(scat_code),
        ).order_by("id").first()
    except Exception:
        return None


PACHWAI_MODULE_CODE = "NLI_ADD_PACHWAI"
DRAUGHT_BEER_MODULE_CODE = "NLI_ADD_DRAUGHT_BEER"


def _get_additional_charge_total(application: NewLicenseApplication) -> Decimal:
    total = Decimal("0.00")
    try:
        from models.transactional.payment_gateway.models import MasterPaymentModule

        module_fees = {
            m["module_code"]: (m["license_fee"] if m["license_fee"] is not None else Decimal("0.00"))
            for m in MasterPaymentModule.objects.filter(
                module_code__in=[PACHWAI_MODULE_CODE, DRAUGHT_BEER_MODULE_CODE],
                visibility_status=True,
            ).values("module_code", "license_fee")
        }
        if getattr(application, "pachwai", False):
            total += module_fees.get(PACHWAI_MODULE_CODE, Decimal("0.00"))
        if getattr(application, "draught_beer", False):
            total += module_fees.get(DRAUGHT_BEER_MODULE_CODE, Decimal("0.00"))
    except Exception:
        pass
    return total


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@parser_classes([JSONParser, FormParser, MultiPartParser])
def pay_license_fee_wallet(request, application_id):
    application = get_object_or_404(NewLicenseApplication, application_id=application_id)
    _require_licensee_user(request)
    if application.applicant_id != request.user.id:
        return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

    lic = _resolve_na_license_for_application(application)
    if not lic:
        return Response({"detail": "License not issued yet."}, status=status.HTTP_400_BAD_REQUEST)

    fee = _resolve_license_fee_row(application)
    if not fee:
        return Response({"detail": "License fee structure not configured for this application."}, status=status.HTTP_400_BAD_REQUEST)

    amount = getattr(fee, "license_fee", None)
    if amount is None:
        return Response({"detail": "License fee amount not configured."}, status=status.HTTP_400_BAD_REQUEST)
    amount = amount + _get_additional_charge_total(application)

    license_fee_hoa = _resolve_hoa_code(module_type="other", wallet_type="license_fee")
    
    txn_id = secrets.token_hex(12).upper()
    try:
        debit_wallet_balance(
            transaction_id=txn_id,
            licensee_id=str(lic.license_id),
            wallet_type="license_fee",
            head_of_account=license_fee_hoa,
            amount=amount,
            user_id=str(getattr(request.user, "username", "") or "").strip(),
            remarks=f"License fee paid for {application.application_id}",
            reference_no=application.application_id,
        )
    except Exception as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    if not application.is_license_fee_paid:
        application.is_license_fee_paid = True
        application.save(update_fields=["is_license_fee_paid"])
    sync_new_license_payment_status(application)

    return Response({"success": True, "transaction_id": txn_id, "is_license_fee_paid": True})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@parser_classes([JSONParser, FormParser, MultiPartParser])
def pay_security_fee_wallet(request, application_id):
    application = get_object_or_404(NewLicenseApplication, application_id=application_id)
    _require_licensee_user(request)
    if application.applicant_id != request.user.id:
        return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

    lic = _resolve_na_license_for_application(application)
    if not lic:
        return Response({"detail": "License not issued yet."}, status=status.HTTP_400_BAD_REQUEST)

    fee = _resolve_license_fee_row(application)
    if not fee:
        return Response({"detail": "License fee structure not configured for this application."}, status=status.HTTP_400_BAD_REQUEST)

    amount = getattr(fee, "security_amount", None)
    if amount is None:
        return Response({"detail": "Security fee amount not configured."}, status=status.HTTP_400_BAD_REQUEST)
    amount = amount + _get_additional_charge_total(application)
    security_deposit_hoa = _resolve_hoa_code(module_type="other", wallet_type="security_deposit")
    txn_id = secrets.token_hex(12).upper()
    try:
        debit_wallet_balance(
            transaction_id=txn_id,
            licensee_id=str(lic.license_id),
            wallet_type="security_deposit",
            head_of_account=security_deposit_hoa,
            amount=amount,
            user_id=str(getattr(request.user, "username", "") or "").strip(),
            remarks=f"Security fee paid for {application.application_id}",
            reference_no=application.application_id,
        )
    except Exception as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    if not application.is_security_fee_paid:
        application.is_security_fee_paid = True
        application.save(update_fields=["is_security_fee_paid"])
    sync_new_license_payment_status(application)

    return Response({"success": True, "transaction_id": txn_id, "is_security_fee_paid": True})

# Dashboard Counts

@permission_classes([HasAppPermission('new_license_application', 'view'), HasStagePermission])
@api_view(['GET'])
def dashboard_counts(request):
    role = _normalize_role(request.user.role.name if request.user.role else None)
    workflow_id = WORKFLOW_IDS['LICENSE_APPROVAL']
    stage_sets = _get_stage_sets(workflow_id)
    all_qs = NewLicenseApplication.objects.all()

    if role == 'licensee':
        base_qs = NewLicenseApplication.objects.filter(applicant=request.user)
        unpaid_qs = base_qs.filter(is_application_fee_paid=False)
        paid_qs = base_qs.filter(is_application_fee_paid=True)
        applied_stages = set(stage_sets['initial'])
        objection_stages = set(stage_sets['objection'])
        approved_stages = set(stage_sets['approved'])
        rejected_stages = set(stage_sets['rejected'])
        pending_stages = set(stage_sets['all']) - applied_stages - approved_stages - rejected_stages - objection_stages

        return Response({
            # Licensee UX: application is considered "Pending" until application-fee payment succeeds.
            "applied": paid_qs.filter(current_stage__name__in=applied_stages).count(),
            "pending": unpaid_qs.count() + paid_qs.filter(current_stage__name__in=pending_stages).count(),
            "objection": paid_qs.filter(current_stage__name__in=objection_stages).count(),
            "approved": paid_qs.filter(current_stage__name__in=approved_stages).count(),
            "rejected": paid_qs.filter(current_stage__name__in=rejected_stages).count(),
        })

    if role in ['site_admin']:
        applied_stages = set(stage_sets['initial'])
        objection_stages = set(stage_sets['objection'])
        approved_stages = set(stage_sets['approved'])
        rejected_stages = set(stage_sets['rejected'])
        pending_stages = set(stage_sets['all']) - applied_stages - approved_stages - rejected_stages - objection_stages

        return Response({
            "applied": all_qs.filter(current_stage__name__in=applied_stages).count(),
            "pending": all_qs.filter(current_stage__name__in=pending_stages).count(),
            "objection": all_qs.filter(current_stage__name__in=objection_stages).count(),
            "approved": all_qs.filter(current_stage__name__in=approved_stages).count(),
            "rejected": all_qs.filter(current_stage__name__in=rejected_stages).count(),
        })

    role_stage_names = _get_role_stage_names(request.user, workflow_id)
    if not role_stage_names:
        return Response({
            "pending": 0,
            "approved": 0,
            "rejected": 0,
        })

    from django.contrib.contenttypes.models import ContentType
    from django.db.models import OuterRef, Exists, Q

    content_type = ContentType.objects.get_for_model(NewLicenseApplication)
    role_id = getattr(getattr(request.user, 'role', None), 'id', None)
    
    acted_by_role = Exists(
        WorkflowTransaction.objects.filter(
            content_type=content_type, 
            object_id=OuterRef('application_id'),
            performed_by__role_id=role_id
        )
    )

    role_objection_stages = set(stage_sets['objection'])
    pending_stages = set(role_stage_names) | role_objection_stages
    role_rejected_stages = set(stage_sets['rejected'])

    pending_count = all_qs.filter(current_stage__name__in=pending_stages).count()
    approved_count = (
        all_qs.exclude(current_stage__name__in=pending_stages | role_rejected_stages)
        .annotate(_acted_by_role=acted_by_role)
        .filter(_acted_by_role=True)
        .count()
    )
    rejected_count = (
        all_qs.filter(current_stage__name__in=role_rejected_stages)
        .annotate(_acted_by_role=acted_by_role)
        .filter(_acted_by_role=True)
        .count()
    )

    return Response({
        "pending": pending_count,
        "approved": approved_count,
        "rejected": rejected_count,
    })

# Application Grouping

@permission_classes([HasAppPermission('new_license_application', 'view'), HasStagePermission])
@api_view(['GET'])
@parser_classes([JSONParser])
def application_group(request):
    role = _normalize_role(request.user.role.name if request.user.role else None)
    workflow_id = WORKFLOW_IDS['LICENSE_APPROVAL']
    stage_sets = _get_stage_sets(workflow_id)
    all_qs = NewLicenseApplication.objects.all()

    if role == 'licensee':
        base_qs = _with_site_enquiry_revert_annotations(
            _with_application_fee_payment_annotations(NewLicenseApplication.objects.filter(applicant=request.user))
        )
        unpaid_qs = base_qs.filter(is_application_fee_paid=False)
        paid_qs = base_qs.filter(is_application_fee_paid=True)
        applied_stages = set(stage_sets['initial'])
        objection_stages = set(stage_sets['objection'])
        approved_stages = set(stage_sets['approved'])
        rejected_stages = set(stage_sets['rejected'])
        pending_stages = set(stage_sets['all']) - applied_stages - approved_stages - rejected_stages - objection_stages

        from django.db.models import Q
        pending_qs = base_qs.filter(
            Q(is_application_fee_paid=False)
            | (Q(is_application_fee_paid=True) & Q(current_stage__name__in=pending_stages))
        )

        return Response({
            "applied": NewLicenseApplicationSerializer(
                paid_qs.filter(current_stage__name__in=applied_stages), many=True
            ).data,
            "pending": NewLicenseApplicationSerializer(
                pending_qs, many=True
            ).data,
            "objection": NewLicenseApplicationSerializer(
                paid_qs.filter(current_stage__name__in=objection_stages), many=True
            ).data,
            "approved": NewLicenseApplicationSerializer(
                paid_qs.filter(current_stage__name__in=approved_stages), many=True
            ).data,
            "rejected": NewLicenseApplicationSerializer(
                paid_qs.filter(current_stage__name__in=rejected_stages), many=True
            ).data
        })

    if role in ['site_admin']:
        all_qs = _with_site_enquiry_revert_annotations(_with_application_fee_payment_annotations(all_qs))
        applied_stages = set(stage_sets['initial'])
        objection_stages = set(stage_sets['objection'])
        approved_stages = set(stage_sets['approved'])
        rejected_stages = set(stage_sets['rejected'])
        pending_stages = set(stage_sets['all']) - applied_stages - approved_stages - rejected_stages - objection_stages

        return Response({
            "applied": NewLicenseApplicationSerializer(
                all_qs.filter(current_stage__name__in=applied_stages), many=True
            ).data,
            "pending": NewLicenseApplicationSerializer(
                all_qs.filter(current_stage__name__in=pending_stages), many=True
            ).data,
            "objection": NewLicenseApplicationSerializer(
                all_qs.filter(current_stage__name__in=objection_stages), many=True
            ).data,
            "approved": NewLicenseApplicationSerializer(
                all_qs.filter(current_stage__name__in=approved_stages), many=True
            ).data,
            "rejected": NewLicenseApplicationSerializer(
                all_qs.filter(current_stage__name__in=rejected_stages), many=True
            ).data
        })

    role_stage_names = _get_role_stage_names(request.user, workflow_id)
    if role_stage_names:
        all_qs = _with_site_enquiry_revert_annotations(_with_application_fee_payment_annotations(all_qs))
        from django.contrib.contenttypes.models import ContentType
        from django.db.models import OuterRef, Exists, Q

        content_type = ContentType.objects.get_for_model(NewLicenseApplication)
        role_id = getattr(getattr(request.user, 'role', None), 'id', None)
        
        acted_by_role = Exists(
            WorkflowTransaction.objects.filter(
                content_type=content_type, 
                object_id=OuterRef('application_id'),
                performed_by__role_id=role_id
            )
        )

        role_objection_stages = set(stage_sets['objection'])
        pending_stages = set(role_stage_names) | role_objection_stages
        role_rejected_stages = set(stage_sets['rejected'])
        
        approved_qs = (
            all_qs.exclude(current_stage__name__in=pending_stages | role_rejected_stages)
            .annotate(_acted_by_role=acted_by_role)
            .filter(_acted_by_role=True)
        )
        rejected_qs = (
            all_qs.filter(current_stage__name__in=role_rejected_stages)
            .annotate(_acted_by_role=acted_by_role)
            .filter(_acted_by_role=True)
        )

        return Response({
             "applied": [],
             "pending": NewLicenseApplicationSerializer(
                 all_qs.filter(current_stage__name__in=pending_stages), many=True
             ).data,
             "objection": NewLicenseApplicationSerializer(
                 all_qs.filter(current_stage__name__in=role_objection_stages), many=True
             ).data,
             "approved": NewLicenseApplicationSerializer(
                 approved_qs, many=True
             ).data,
             "rejected": NewLicenseApplicationSerializer(
                 rejected_qs, many=True
             ).data
        })

    return Response({
         "applied": [],
         "pending": [],
         "objection": [],
         "approved": [],
         "rejected": []
    })
