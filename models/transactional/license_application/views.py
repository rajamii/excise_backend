from django.shortcuts import get_object_or_404
from datetime import date, timedelta
from django.db import transaction
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.parsers import JSONParser, MultiPartParser, FormParser
from rest_framework.response import Response
from auth.roles.permissions import HasAppPermission
from .models import LicenseApplication
from models.masters.license.models import License, LicenseValidationToken
from models.masters.core.models import LicenseFee
from .serializers import LicenseApplicationSerializer, LicenseFeeSerializer
from rest_framework import status
from auth.workflow.models import Workflow, WorkflowStage
from auth.workflow.constants import WORKFLOW_IDS
from auth.workflow.permissions import HasStagePermission
from auth.workflow.services import WorkflowService
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
from django.http import FileResponse, HttpResponse
from io import BytesIO
import base64
import mimetypes
from PIL import Image
from utils.qrcodegen import QrCode
import re
from models.masters.license.master_license_form import MasterLicenseForm
from models.masters.license.master_license_form_terms import MasterLicenseFormTerms
from models.masters.license.legacy_codes import resolve_codes_for_license_form
from django.core import signing
from urllib.parse import quote
import secrets
import hashlib


def _normalize_role(role_name):
    if not role_name:
        return None
    normalized = str(role_name).strip().lower().replace('-', '_').replace(' ', '_')
    aliases = {
        'license_user': 'licensee',
        'licensee_user': 'licensee',
        'permit_section': 'permit_section',
        'singlewindow': 'single_window',
        'siteadmin': 'site_admin',
    }
    return aliases.get(normalized, normalized)


def _ensure_license_validation_nonce(license_obj: License | None) -> str:
    if not license_obj:
        return ''

    try:
        latest = LicenseValidationToken.objects.filter(license=license_obj).order_by('-created_at').first()
        if latest and latest.nonce:
            # keep license.validation_nonce as a handy "latest" cache
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
        # Collision is extremely unlikely, but retry once.
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

def _create_application(request, workflow_id: int, serializer_cls):
    
    serializer = serializer_cls(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    with transaction.atomic():
        workflow = get_object_or_404(Workflow, id=workflow_id)
        initial_stage = workflow.stages.get(is_initial=True)
        district_code = serializer.validated_data['excise_district'].district_code

        # Lock rows with same prefix and get the last number
        prefix = f"LIC/{district_code}/{LicenseApplication.generate_fin_year()}"
        last_app = LicenseApplication.objects.filter(
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

        WorkflowService.submit_application(
            application=application,
            user=request.user,
            remarks="Application submitted",
        )

        fresh = LicenseApplication.objects.get(pk=application.pk)
        fresh_serializer = serializer_cls(fresh)
        return Response(fresh_serializer.data, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@parser_classes([MultiPartParser, FormParser, JSONParser])
@permission_classes([HasStagePermission])
def create_license_application(request):
    return _create_application(request, WORKFLOW_IDS['LICENSE_APPROVAL'], LicenseApplicationSerializer)


@api_view(['POST'])
@permission_classes([HasStagePermission])
def initiate_renewal(request, license_id):
    """
    Initiate renewal by creating a pre-filled new application from an existing license.
    """
    old_license = get_object_or_404(License, license_id=license_id, source_type='license_application')

    old_app = old_license.source_application
    if not isinstance(old_app, LicenseApplication):
        return Response({"detail": "Invalid license source."}, status=status.HTTP_400_BAD_REQUEST)

    if old_app.applicant != request.user:
        return Response({"detail": "You can only renew your own license."}, status=status.HTTP_403_FORBIDDEN)

    today = date.today()
    if old_license.valid_up_to > today + timedelta(days=90):
        return Response({
            "detail": f"Renewal not allowed yet. License valid until {old_license.valid_up_to.strftime('%d/%m/%Y')}. "
                     "You can renew within the last 90 days or after expiry."
        }, status=status.HTTP_400_BAD_REQUEST)

    # Build pre-filled data
    new_data = {
        'excise_district': old_app.excise_district,
        'license_category': old_app.license_category,
        'excise_subdivision': old_app.excise_subdivision,
        'license': old_app.license,
        'license_type': old_app.license_type,
        'establishment_name': old_app.establishment_name,
        'mobile_number': old_app.mobile_number,
        'email': old_app.email,
        'license_no': old_app.license_no,
        'initial_grant_date': old_app.initial_grant_date,
        'renewed_from': old_app.renewed_from,
        'valid_up_to': old_app.valid_up_to,
        'yearly_license_fee': old_app.yearly_license_fee,
        'license_nature': old_app.license_nature,
        'functioning_status': old_app.functioning_status,
        'mode_of_operation': old_app.mode_of_operation,
        'site_subdivision': old_app.site_subdivision,
        'police_station': old_app.police_station,
        'location_category': old_app.location_category,
        'location_name': old_app.location_name,
        'ward_name': old_app.ward_name,
        'business_address': old_app.business_address,
        'road_name': old_app.road_name,
        'pin_code': old_app.pin_code,
        'latitude': old_app.latitude,
        'longitude': old_app.longitude,
        'company_name': old_app.company_name,
        'company_address': old_app.company_address,
        'company_pan': old_app.company_pan,
        'company_cin': old_app.company_cin,
        'incorporation_date': old_app.incorporation_date,
        'company_phone_number': old_app.company_phone_number,
        'company_email': old_app.company_email,
        'status' : old_app.status,
        'member_name': old_app.member_name,
        'father_husband_name': old_app.father_husband_name,
        'nationality': old_app.nationality,
        'gender': old_app.gender,
        'pan': old_app.pan,
        'member_mobile_number': old_app.member_mobile_number,
        'member_email': old_app.member_email,
        'photo': old_app.photo,
    }

    # Manual creation to handle files/IDs
    district_code = str(old_app.excise_district.district_code)
    fin_year = LicenseApplication.generate_fin_year()
    prefix = f"LIC/{district_code}/{fin_year}"

    with transaction.atomic():
        last_app = LicenseApplication.objects.filter(
            application_id__startswith=prefix
        ).select_for_update().order_by('-application_id').first()

        last_number = int(last_app.application_id.split('/')[-1]) if last_app else 0
        new_number = str(last_number + 1).zfill(4)
        new_application_id = f"{prefix}/{new_number}"

        workflow = get_object_or_404(Workflow, id=WORKFLOW_IDS['LICENSE_APPROVAL'])
        initial_stage = workflow.stages.get(is_initial=True)

        new_application = LicenseApplication.objects.create(
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
        remarks="Renewal application"
    )

    serializer = LicenseApplicationSerializer(new_application)
    return Response({
        "detail": "Renewal application initiated and submitted successfully.",
        "application": serializer.data
    }, status=status.HTTP_201_CREATED)


@permission_classes([HasAppPermission('license_application', 'view'), HasStagePermission])
@api_view(['GET'])
def list_license_applications(request):
    role = _normalize_role(request.user.role.name if request.user.role else None)

    if role in ["single_window","site_admin"]:
        applications = LicenseApplication.objects.all()
    elif role == "licensee":
        applications = LicenseApplication.objects.filter(applicant=request.user)
    else:
        applications = LicenseApplication.objects.filter(
            current_stage__stagepermission__role=request.user.role,
            current_stage__stagepermission__can_process=True
        ).distinct()

    serializer = LicenseApplicationSerializer(applications, many=True)
    return Response(serializer.data)


@permission_classes([HasAppPermission('license_application', 'view')])
@api_view(['GET'])
def license_application_detail(request, pk):
    raw_pk = str(pk or "").strip()
    if raw_pk.isdigit():
        application = get_object_or_404(LicenseApplication, pk=int(raw_pk))
    else:
        application = get_object_or_404(LicenseApplication, application_id=raw_pk)

    role = _normalize_role(request.user.role.name if request.user.role else None)
    if role == "licensee" and application.applicant_id != request.user.id:
        return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

    serializer = LicenseApplicationSerializer(application)
    return Response(serializer.data)


@permission_classes([HasAppPermission('license_application', 'view')])
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
        if isinstance(payload, dict) and payload.get("source") == "license_application" and payload.get("applicationId"):
            resolved_application_id = str(payload["applicationId"])
            validated_via_code = True
    except Exception:
        resolved_application_id = raw_id

    application = get_object_or_404(LicenseApplication, application_id=resolved_application_id)

    role = _normalize_role(request.user.role.name if request.user.role else None)
    if role == "licensee" and application.applicant_id != request.user.id:
        return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

    la_ct = ContentType.objects.get_for_model(LicenseApplication)
    license_obj = License.objects.filter(
        source_type="license_application",
        source_content_type=la_ct,
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

    photo_url = ""
    photo_exists = False
    passport_photo_data_url = ""
    try:
        if application.photo and hasattr(application.photo, "url"):
            photo_url = request.build_absolute_uri(application.photo.url)
            photo_exists = application.photo.storage.exists(application.photo.name)
            if photo_exists:
                try:
                    with application.photo.open("rb") as f:
                        raw = f.read()
                    mime = mimetypes.guess_type(application.photo.name)[0] or "application/octet-stream"
                    b64 = base64.b64encode(raw).decode("ascii")
                    passport_photo_data_url = f"data:{mime};base64,{b64}"
                except Exception:
                    passport_photo_data_url = ""
    except Exception:
        photo_url = ""
        photo_exists = False
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

    license_number = ""
    if license_obj:
        license_number = license_obj.license_id
    elif getattr(application, "license_no", None):
        license_number = str(application.license_no)
    else:
        license_number = application.application_id

    cat_code = getattr(license_obj, "license_category_id", None) if license_obj else None
    scat_code = getattr(license_obj, "license_sub_category_id", None) if license_obj else None
    if cat_code is None:
        cat_code = getattr(application, "license_category_id", None)

    resolved_cat = None
    resolved_scat = None
    if cat_code is not None and scat_code is not None:
        resolved_cat, resolved_scat = resolve_codes_for_license_form(int(cat_code), int(scat_code))

    license_title = ""
    terms: list[str] = []
    if resolved_cat is not None and resolved_scat is not None:
        cfg = MasterLicenseForm.get_license_config(int(resolved_cat), int(resolved_scat))
        license_title = cfg.license_title if cfg else ""

        qs = MasterLicenseFormTerms.objects.filter(
            licensee_cat_code=int(resolved_cat),
            licensee_scat_code=int(resolved_scat),
        ).order_by("sl_no")
        terms = [str(t.license_terms).strip() for t in qs if getattr(t, "license_terms", None)]
        terms = [t for t in terms if t]

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
                    request, application_id=application.application_id, source="license_application", nonce=nonce
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
        "licenseNumber": license_number,
        "licenseTitle": license_title,
        "validationCode": validation_code,
        "validationPdfUrl": validation_url,
        "validatedViaCode": validated_via_code,
        "print_count": int(getattr(license_obj, "print_count", 0) or 0) if license_obj else 0,
        "is_print_fee_paid": bool(getattr(license_obj, "is_print_fee_paid", False)) if license_obj else False,
        "terms": terms,
        # Debug/compat fields: the (legacy) codes used to pick terms/title.
        # Frontend can ignore these safely.
        "termsCatCode": resolved_cat,
        "termsScatCode": resolved_scat,
        "licenseeName": application.member_name or application.establishment_name,
        "fatherOrHusbandName": application.father_husband_name,
        "kindOfShop": application.license_type.license_type if getattr(application, "license_type", None) else "",
        "addressOfBusiness": build_address(),
        "district": application.excise_district.district if application.excise_district else "",
        "modeOfOperation": application.mode_of_operation or "",
        "passportPhotoUrl": photo_url,
        "passportPhotoExists": photo_exists,
        "passportPhotoDataUrl": passport_photo_data_url,
        "licenseFee": application.yearly_license_fee or "",
        "transactionRef": "",
        "transactionDate": "",
        "validFrom": fmt_dt(license_obj.issue_date) if license_obj else "",
        "validTo": fmt_dt(license_obj.valid_up_to) if license_obj else (fmt_dt(application.valid_up_to) if getattr(application, "valid_up_to", None) else ""),
        "generatedOn": fmt_dt(timezone.now().date()),
        "qrCodeDataUrl": make_qr_data_url(validation_url),
    }
    return Response(response, status=status.HTTP_200_OK)


@permission_classes([HasAppPermission('license_application', 'view')])
@api_view(['GET'])
def final_license_passport_photo(request, application_id):
    application = get_object_or_404(LicenseApplication, application_id=application_id)

    role = _normalize_role(request.user.role.name if request.user.role else None)
    if role == "licensee" and application.applicant_id != request.user.id:
        return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

    if not getattr(application, "photo", None):
        return Response({"detail": "Photo not available."}, status=status.HTTP_404_NOT_FOUND)

    try:
        f = application.photo.open("rb")
    except Exception:
        return Response({"detail": "Photo not available."}, status=status.HTTP_404_NOT_FOUND)

    return FileResponse(f, content_type="image/jpeg")


@permission_classes([HasAppPermission('license_application', 'view')])
@api_view(['GET'])
def final_license_qr_code(request, application_id):
    application = get_object_or_404(LicenseApplication, application_id=application_id)

    role = _normalize_role(request.user.role.name if request.user.role else None)
    if role == "licensee" and application.applicant_id != request.user.id:
        return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

    la_ct = ContentType.objects.get_for_model(LicenseApplication)
    license_obj = License.objects.filter(
        source_type="license_application",
        source_content_type=la_ct,
        source_object_id=application.application_id,
    ).order_by("-issue_date").first()

    # Keep the license's cached "latest nonce" in sync with token history.
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
                    request, application_id=application.application_id, source="license_application", nonce=nonce
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


@permission_classes([HasAppPermission('license_application', 'update')])
@api_view(['POST'])
@parser_classes([JSONParser])
def print_license_view(request, application_id):
    license = get_object_or_404(LicenseApplication, application_id=application_id)

    la_ct = ContentType.objects.get_for_model(LicenseApplication)
    license_obj = License.objects.filter(
        source_type="license_application",
        source_content_type=la_ct,
        source_object_id=license.application_id,
    ).order_by("-issue_date").first()

    # If a License exists but application approval flag isn't synced, allow printing.
    if not license.is_approved and not license_obj:
        return Response({"error": "License is not approved yet."}, status=403)

    can_print, fee = license.can_print_license()

    if not can_print:
        return Response({
            "error": "Print limit exceeded. Please pay ₹500 to continue printing.",
            "fee_required": fee
        }, status=403)

    if fee > 0 and not license.is_print_fee_paid:
        return Response({"error": "₹500 fee not paid yet."}, status=403)

    license.record_license_print(fee_paid=(fee > 0))

    if license_obj:
        # New token per print; old tokens remain valid for future verification.
        nonce = secrets.token_hex(16)
        signed_code, full_url, verification_id = _build_validation_link(
            request, application_id=license.application_id, source="license_application", nonce=nonce
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
                request, application_id=license.application_id, source="license_application", nonce=nonce
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
        "print_count": license.print_count,
        "validationCode": validation_code,
        "validationPdfUrl": validation_url,
    })

@permission_classes([HasAppPermission('license_application', 'view')])
@api_view(['GET'])
def get_location_fees(request):
    fees = LicenseFee.objects.all()
    serializer = LicenseFeeSerializer(fees, many=True)
    return Response(serializer.data)


@permission_classes([HasAppPermission('license_application', 'view'), HasStagePermission])
@api_view(['GET'])
def dashboard_counts(request):
    role = _normalize_role(request.user.role.name if request.user.role else None)
    workflow_id = WORKFLOW_IDS['LICENSE_APPROVAL']
    stage_sets = _get_stage_sets(workflow_id)
    all_qs = LicenseApplication.objects.all()

    if role == 'licensee':
        base_qs = LicenseApplication.objects.filter(applicant=request.user)
        applied_stages = stage_sets['initial'] | stage_sets['level']
        pending_stages = stage_sets['objection'] | stage_sets['payment']
        return Response({
            "applied": base_qs.filter(current_stage__name__in=applied_stages).count(),
            "pending": base_qs.filter(current_stage__name__in=pending_stages).count(),
            "approved": base_qs.filter(current_stage__name__in=stage_sets['approved'], is_approved=True).count(),
            "rejected": base_qs.filter(current_stage__name__in=stage_sets['rejected']).count(),
        })

    if role in ['site_admin', 'single_window']:
        applied_stages = stage_sets['initial'] | stage_sets['level']
        pending_stages = stage_sets['objection'] | stage_sets['payment']
        return Response({
            "applied": all_qs.filter(current_stage__name__in=applied_stages).count(),
            "pending": all_qs.filter(current_stage__name__in=pending_stages).count(),
            "approved": all_qs.filter(current_stage__name__in=stage_sets['approved'], is_approved=True).count(),
            "rejected": all_qs.filter(current_stage__name__in=stage_sets['rejected']).count(),
        })

    role_stage_names = _get_role_stage_names(request.user, workflow_id)
    if not role_stage_names:
        return Response({"detail": "Invalid role"}, status=status.HTTP_400_BAD_REQUEST)

    role_level_indexes = [
        stage_sets['level_indexes'][name]
        for name in role_stage_names
        if name in stage_sets['level_indexes']
    ]
    max_role_level = max(role_level_indexes) if role_level_indexes else None

    role_objection_stages = set()
    for stage_name in role_stage_names:
        index = _extract_level_index(stage_name)
        candidate = f'level_{index}_objection' if index else None
        if candidate and candidate in stage_sets['all']:
            role_objection_stages.add(candidate)

    forward_stages = set(stage_sets['approved']) | set(stage_sets['payment'])
    if max_role_level is not None:
        forward_stages.update({
            name for name, idx in stage_sets['level_indexes'].items()
            if idx and idx > max_role_level
        })

    role_rejected_stages = {
        f'rejected_by_{stage_name}'
        for stage_name in role_stage_names
        if f'rejected_by_{stage_name}' in stage_sets['all']
    }
    if 'rejected' in stage_sets['all']:
        role_rejected_stages.add('rejected')

    return Response({
        "pending": all_qs.filter(current_stage__name__in=(role_stage_names | role_objection_stages)).count(),
        "approved": all_qs.filter(current_stage__name__in=forward_stages).count(),
        "rejected": all_qs.filter(current_stage__name__in=role_rejected_stages).count(),
    })



@permission_classes([HasAppPermission('license_application', 'view'), HasStagePermission])
@api_view(['GET'])
@parser_classes([JSONParser])
def application_group(request):
    role = _normalize_role(request.user.role.name if request.user.role else None)
    workflow_id = WORKFLOW_IDS['LICENSE_APPROVAL']
    stage_sets = _get_stage_sets(workflow_id)
    all_qs = LicenseApplication.objects.all()

    if role == 'licensee':
        base_qs = LicenseApplication.objects.filter(applicant=request.user)
        applied_stages = stage_sets['initial'] | stage_sets['level']
        pending_stages = stage_sets['objection'] | stage_sets['payment']
        result = {
            "applied": LicenseApplicationSerializer(
               base_qs.filter(current_stage__name__in=applied_stages),
                many=True
            ).data,
            "pending": LicenseApplicationSerializer(
                base_qs.filter(current_stage__name__in=pending_stages),
                many=True
            ).data,
            "approved": LicenseApplicationSerializer(
                base_qs.filter(current_stage__name__in=stage_sets['approved']),
                many=True
            ).data,
            "rejected": LicenseApplicationSerializer(
                base_qs.filter(current_stage__name__in=stage_sets['rejected']),
                many=True
            ).data
        }
        return Response(result)

    if role in ['site_admin', 'single_window']:
        applied_stages = stage_sets['initial'] | stage_sets['level']
        pending_stages = stage_sets['objection'] | stage_sets['payment']
        return Response({
            "applied": LicenseApplicationSerializer(
                all_qs.filter(current_stage__name__in=applied_stages), many=True
            ).data,
            "pending": LicenseApplicationSerializer(
                all_qs.filter(current_stage__name__in=pending_stages), many=True
            ).data,
            "approved": LicenseApplicationSerializer(
                all_qs.filter(current_stage__name__in=stage_sets['approved']), many=True
            ).data,
            "rejected": LicenseApplicationSerializer(
                all_qs.filter(current_stage__name__in=stage_sets['rejected']), many=True
            ).data
        })

    role_stage_names = _get_role_stage_names(request.user, workflow_id)
    if role_stage_names:
        role_level_indexes = [
            stage_sets['level_indexes'][name]
            for name in role_stage_names
            if name in stage_sets['level_indexes']
        ]
        max_role_level = max(role_level_indexes) if role_level_indexes else None

        role_objection_stages = set()
        for stage_name in role_stage_names:
            index = _extract_level_index(stage_name)
            candidate = f'level_{index}_objection' if index else None
            if candidate and candidate in stage_sets['all']:
                role_objection_stages.add(candidate)

        forward_stages = set(stage_sets['approved']) | set(stage_sets['payment'])
        if max_role_level is not None:
            forward_stages.update({
                name for name, idx in stage_sets['level_indexes'].items()
                if idx and idx > max_role_level
            })

        role_rejected_stages = {
            f'rejected_by_{stage_name}'
            for stage_name in role_stage_names
            if f'rejected_by_{stage_name}' in stage_sets['all']
        }
        if 'rejected' in stage_sets['all']:
            role_rejected_stages.add('rejected')

        return Response({
            "pending": LicenseApplicationSerializer(
                all_qs.filter(current_stage__name__in=(role_stage_names | role_objection_stages)), many=True
            ).data,
            "approved": LicenseApplicationSerializer(
                all_qs.filter(current_stage__name__in=forward_stages), many=True
            ).data,
            "rejected": LicenseApplicationSerializer(
                all_qs.filter(current_stage__name__in=role_rejected_stages), many=True
            ).data
        })

    return Response({"detail": "Invalid role"}, status=status.HTTP_400_BAD_REQUEST)
