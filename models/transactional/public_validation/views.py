from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.core import signing
from django.http import HttpResponse
from django.utils import timezone
from PIL import Image
from rest_framework import status
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from models.masters.license.master_license_form import MasterLicenseForm
from models.masters.license.master_license_form_terms import MasterLicenseFormTerms
from models.masters.license.models import License
from models.transactional.license_application.models import LicenseApplication
from models.transactional.new_license_application.models import NewLicenseApplication
from utils.simple_pdf import PdfPage, build_text_pdf, build_validation_pdf_multi, paginate_lines


def _normalize_token(raw: str) -> str:
    token = str(raw or '').strip()
    low = token.lower()
    if low.startswith('val:'):
        return token[4:].strip()
    if low.startswith('val-'):
        return token[4:].strip()
    if low.startswith('val '):
        return token[4:].strip()
    return token


def _fmt_dt(d) -> str:
    return d.strftime('%d/%m/%Y') if d else ''


def _build_address_from_application(app) -> str:
    parts: list[str] = []
    if getattr(app, 'location_name', None):
        parts.append(str(app.location_name).strip())
    if getattr(app, 'ward_name', None):
        parts.append(f"Ward: {str(app.ward_name).strip()}")
    if getattr(app, 'business_address', None):
        parts.append(str(app.business_address).strip())
    if getattr(app, 'police_station', None) and getattr(app.police_station, 'police_station', None):
        parts.append(f"P.S - {app.police_station.police_station}")
    if getattr(app, 'site_subdivision', None) and getattr(app.site_subdivision, 'subdivision', None):
        parts.append(f"Sub Division - {app.site_subdivision.subdivision}")
    if getattr(app, 'pin_code', None):
        parts.append(f"Pin - {app.pin_code}")
    return ', '.join([p for p in parts if p])


def _resolve_license_obj(source: str, application_id: str, model_cls):
    ct = ContentType.objects.get_for_model(model_cls)
    return (
        License.objects.filter(
            source_type=source,
            source_content_type=ct,
            source_object_id=application_id,
        )
        .order_by('-issue_date')
        .first()
    )


def _fetch_title_terms(cat_code: int | None, scat_code: int | None) -> tuple[str, list[str]]:
    if cat_code is None or scat_code is None:
        return '', []

    cfg = MasterLicenseForm.get_license_config(int(cat_code), int(scat_code))
    title = cfg.license_title if cfg else ''

    qs = (
        MasterLicenseFormTerms.objects.filter(
            licensee_cat_code=int(cat_code),
            licensee_scat_code=int(scat_code),
        )
        .order_by('sl_no')
        .all()
    )
    terms = [str(t.license_terms).strip() for t in qs if getattr(t, 'license_terms', None)]
    terms = [t for t in terms if t]
    return title, terms


def _build_pdf_lines(payload: dict) -> list[str]:
    title = str(payload.get('licenseTitle') or '').strip()
    license_number = str(payload.get('licenseNumber') or '').strip()
    validated = bool(payload.get('validatedViaCode'))
    code = str(payload.get('validationCode') or '').strip()
    pdf_url = str(payload.get('validationPdfUrl') or '').strip()

    lines: list[str] = []
    lines.append('EXCISE DEPARTMENT - Government of Sikkim')
    if title:
        lines.append(f'LICENSE TITLE: {title}')
    lines.append('')
    lines.append(f'License No: {license_number}')
    lines.append(f"Name of the Licensee: {payload.get('licenseeName') or ''}")
    lines.append(f"Father/Husband Name: {payload.get('fatherOrHusbandName') or ''}")
    lines.append(f"Kind of Shop: {payload.get('kindOfShop') or ''}")
    lines.append(f"Address: {payload.get('addressOfBusiness') or ''}")
    lines.append(f"District: {payload.get('district') or ''}")
    lines.append(f"Mode of Operation: {payload.get('modeOfOperation') or ''}")
    if payload.get('validFrom') or payload.get('validTo'):
        lines.append(f"Valid From: {payload.get('validFrom') or ''}   Valid To: {payload.get('validTo') or ''}")
    lines.append(f"Generated On: {payload.get('generatedOn') or ''}")
    lines.append('')
    lines.append(f"VALIDATION: {'VERIFIED' if validated else 'NOT VERIFIED'}")
    if code:
        lines.append(f'Validation Code: {code}')
    if pdf_url:
        lines.append(f'Validation PDF URL: {pdf_url}')
    lines.append('')

    terms = payload.get('terms') or []
    if isinstance(terms, list) and terms:
        lines.append('Terms and Conditions:')
        for idx, t in enumerate(terms, start=1):
            lines.append(f'{idx}. {t}')

    return lines


def _load_branding_images():
    base_dir = Path(getattr(settings, 'BASE_DIR', Path('.')))
    logo_path = base_dir / 'static' / 'validation' / 'sikkim-logo.png'
    watermark_path = base_dir / 'static' / 'validation' / 'watermark.png'

    logo_img = None
    watermark_img = None

    try:
        if logo_path.exists():
            logo_img = Image.open(str(logo_path))
    except Exception:
        logo_img = None

    try:
        if watermark_path.exists():
            wm = Image.open(str(watermark_path)).convert('RGBA')
            wm.putalpha(35)
            watermark_img = wm
    except Exception:
        watermark_img = None

    return logo_img, watermark_img


def _make_qr_image(payload: str):
    try:
        from utils.qrcodegen import QrCode

        qr = QrCode.encode_text(str(payload), QrCode.Ecc.MEDIUM)
        size = qr.get_size()
        border = 2
        scale = 4
        img_size = (size + border * 2) * scale
        img = Image.new('RGB', (img_size, img_size), 'white')
        pixels = img.load()
        for y in range(size):
            for x in range(size):
                if qr.get_module(x, y):
                    for dy in range(scale):
                        for dx in range(scale):
                            px = (x + border) * scale + dx
                            py = (y + border) * scale + dy
                            pixels[px, py] = (0, 0, 0)
        return img
    except Exception:
        return None


def _validate_license_pdf_from_code(request, code: str):
    token = _normalize_token(code)
    try:
        payload = signing.loads(token, salt='final-license')
    except Exception:
        return Response({'detail': 'Invalid validation code.'}, status=status.HTTP_400_BAD_REQUEST)

    if not isinstance(payload, dict):
        return Response({'detail': 'Invalid validation code.'}, status=status.HTTP_400_BAD_REQUEST)

    source = str(payload.get('source') or '').strip()
    application_id = str(payload.get('applicationId') or '').strip()
    if not source or not application_id:
        return Response({'detail': 'Invalid validation code.'}, status=status.HTTP_400_BAD_REQUEST)

    now_date = timezone.now().date()
    validation_pdf_url = request.build_absolute_uri('/v/' + quote(token, safe=':') + '/')

    if source == 'new_license_application':
        app = NewLicenseApplication.objects.filter(application_id=application_id).first()
        if not app:
            return Response({'detail': 'License not found.'}, status=status.HTTP_404_NOT_FOUND)

        lic = _resolve_license_obj(source, app.application_id, NewLicenseApplication)
        license_number = lic.license_id if lic else app.application_id
        cat_code = getattr(lic, 'license_category_id', None) if lic else getattr(app, 'license_category_id', None)
        scat_code = getattr(lic, 'license_sub_category_id', None) if lic else getattr(app, 'license_sub_category_id', None)
        license_title, terms = _fetch_title_terms(cat_code, scat_code)

        response_payload = {
            'applicationId': app.application_id,
            'licenseNumber': license_number,
            'licenseTitle': license_title,
            'licenseeName': app.applicant_name,
            'fatherOrHusbandName': app.father_husband_name,
            'kindOfShop': app.license_type.license_type if getattr(app, 'license_type', None) else '',
            'addressOfBusiness': _build_address_from_application(app),
            'district': app.site_district.district if getattr(app, 'site_district', None) else '',
            'modeOfOperation': app.get_mode_of_operation_display() if hasattr(app, 'get_mode_of_operation_display') else getattr(app, 'mode_of_operation', ''),
            'validFrom': _fmt_dt(lic.issue_date) if lic else _fmt_dt(getattr(app, 'created_at', None).date() if getattr(app, 'created_at', None) else None),
            'validTo': _fmt_dt(lic.valid_up_to) if lic else '',
            'generatedOn': _fmt_dt(now_date),
            'validationCode': token,
            'validationPdfUrl': validation_pdf_url,
            'validatedViaCode': True,
            'terms': terms,
        }

    elif source == 'license_application':
        app = LicenseApplication.objects.filter(application_id=application_id).first()
        if not app:
            return Response({'detail': 'License not found.'}, status=status.HTTP_404_NOT_FOUND)

        lic = _resolve_license_obj(source, app.application_id, LicenseApplication)
        if lic:
            license_number = lic.license_id
        elif getattr(app, 'license_no', None):
            license_number = str(app.license_no)
        else:
            license_number = app.application_id

        cat_code = getattr(lic, 'license_category_id', None) if lic else getattr(app, 'license_category_id', None)
        scat_code = getattr(lic, 'license_sub_category_id', None) if lic else None
        license_title, terms = _fetch_title_terms(cat_code, scat_code)

        response_payload = {
            'applicationId': app.application_id,
            'licenseNumber': license_number,
            'licenseTitle': license_title,
            'licenseeName': app.member_name or app.establishment_name,
            'fatherOrHusbandName': app.father_husband_name,
            'kindOfShop': app.license_type.license_type if getattr(app, 'license_type', None) else '',
            'addressOfBusiness': _build_address_from_application(app),
            'district': app.excise_district.district if getattr(app, 'excise_district', None) else '',
            'modeOfOperation': getattr(app, 'mode_of_operation', '') or '',
            'validFrom': _fmt_dt(lic.issue_date) if lic else '',
            'validTo': _fmt_dt(lic.valid_up_to) if lic else (_fmt_dt(getattr(app, 'valid_up_to', None)) if getattr(app, 'valid_up_to', None) else ''),
            'generatedOn': _fmt_dt(now_date),
            'validationCode': token,
            'validationPdfUrl': validation_pdf_url,
            'validatedViaCode': True,
            'terms': terms,
        }

    else:
        return Response({'detail': 'Unsupported license source.'}, status=status.HTTP_400_BAD_REQUEST)

    lines = _build_pdf_lines(response_payload)
    paged = paginate_lines(lines, max_chars=95, lines_per_page=52)

    logo_img, watermark_img = _load_branding_images()
    qr_img = _make_qr_image(validation_pdf_url)

    # Always use the styled PDF generator (multi-page supported)
    pdf = build_validation_pdf_multi(
        pages_lines=paged,
        watermark=watermark_img,
        logo=logo_img,
        qr=qr_img,
        font_size=10,
        header_each_page=True,
    )

    safe_name = ''.join([c if c.isalnum() or c in ('-', '_') else '_' for c in response_payload['licenseNumber']])[:80]
    filename = f"license_validation_{safe_name or 'document'}.pdf"
    resp = HttpResponse(pdf, content_type='application/pdf')
    resp['Content-Disposition'] = f'attachment; filename="{filename}"'
    return resp


@permission_classes([AllowAny])
@authentication_classes([])
@api_view(['GET'])
def validate_license_pdf(request, code: str):
    return _validate_license_pdf_from_code(request, code)


@permission_classes([AllowAny])
@authentication_classes([])
@api_view(['GET'])
def validate_license_pdf_qs(request):
    code = str(request.query_params.get('code') or '').strip()
    if not code:
        return Response({'detail': 'code is required'}, status=status.HTTP_400_BAD_REQUEST)
    return _validate_license_pdf_from_code(request, code)

