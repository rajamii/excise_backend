from __future__ import annotations

import hashlib
import html
from pathlib import Path
from urllib.parse import quote

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.core import signing
from django.core.cache import cache
from django.http import HttpResponse
from django.utils import timezone
from django.views.decorators.http import require_GET
from PIL import Image, ImageChops, ImageFilter
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

_BRANDING_CACHE: tuple[object|None, object|None] | None = None
_WATERMARK_DATA_URL: str | None = None


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

    def _chunk(text: str, *, size: int = 72) -> list[str]:
        raw = str(text or '')
        if not raw:
            return []
        return [raw[i : i + size] for i in range(0, len(raw), size)]

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

    lines.append('VALIDATION:')
    if validated:
        lines.append('__VALID_OK__VERIFIED')
    else:
        lines.append('__VALID_BAD__NOT VERIFIED')

    if code:
        lines.append('Validation Code:')
        for part in _chunk(code, size=72):
            lines.append(f'  {part}')

    if pdf_url:
        lines.append('Validation PDF URL:')
        for part in _chunk(pdf_url, size=72):
            lines.append(f'  {part}')
    lines.append('')

    return lines


def _load_branding_images():
    global _BRANDING_CACHE
    if _BRANDING_CACHE is not None:
        return _BRANDING_CACHE

    base_dir = Path(getattr(settings, 'BASE_DIR', Path('.')))

    # NOTE:
    # - watermark.png is the "boxed" emblem; use it at the top as the header logo.
    # - For the big center watermark, we generate a cleaned version by keying out the
    #   background color and applying a low opacity so it doesn't hurt readability.
    top_logo_path = base_dir / 'static' / 'validation' / 'watermark.png'
    center_watermark_path = base_dir / 'static' / 'validation' / 'sikkim-logo.png'

    logo_img = None
    watermark_img = None

    try:
        if top_logo_path.exists():
            logo_img = Image.open(str(top_logo_path)).convert('RGBA')
            # Make it a small boxed emblem in the header.
            logo_img.putalpha(255)
    except Exception:
        logo_img = None

    def _make_clean_watermark(img: Image.Image, *, opacity: int = 90, threshold: int = 18) -> Image.Image:
        wm = img.convert('RGBA')
        w, h = wm.size
        corners = [
            wm.getpixel((0, 0)),
            wm.getpixel((w - 1, 0)),
            wm.getpixel((0, h - 1)),
            wm.getpixel((w - 1, h - 1)),
        ]
        bg_rgb = tuple(int(round(sum(px[i] for px in corners) / len(corners))) for i in range(3))
        diff = ImageChops.difference(wm.convert('RGB'), Image.new('RGB', wm.size, bg_rgb)).convert('L')
        mask = diff.point(lambda p: 0 if p <= threshold else 255).filter(ImageFilter.GaussianBlur(radius=1))

        # Build a darker, cleaner watermark by using a solid dark color + computed alpha.
        alpha = mask.point(lambda p: int((p / 255.0) * opacity))
        out = Image.new('RGBA', wm.size, (0, 0, 0, 0))
        out.putalpha(alpha)
        return out
    try:
        wm_path = center_watermark_path if center_watermark_path.exists() else top_logo_path
        if wm_path.exists():
            watermark_img = _make_clean_watermark(Image.open(str(wm_path)), opacity=90, threshold=18)
    except Exception:
        watermark_img = None

    _BRANDING_CACHE = (logo_img, watermark_img)
    return _BRANDING_CACHE


def _get_watermark_data_url() -> str:
    global _WATERMARK_DATA_URL
    if _WATERMARK_DATA_URL is not None:
        return _WATERMARK_DATA_URL

    # Prefer the same cleaned watermark used in the PDF generator so it is visible on white backgrounds.
    try:
        _logo_img, wm_img = _load_branding_images()
        if wm_img is not None:
            from io import BytesIO
            import base64

            buf = BytesIO()
            wm_img.save(buf, format='PNG')
            b64 = base64.b64encode(buf.getvalue()).decode('ascii')
            _WATERMARK_DATA_URL = f"data:image/png;base64,{b64}"
            return _WATERMARK_DATA_URL
    except Exception:
        pass

    base_dir = Path(getattr(settings, 'BASE_DIR', Path('.')))
    candidates = [
        base_dir / 'static' / 'validation' / 'sikkim-logo.png',
        base_dir / 'static' / 'validation' / 'watermark.png',
    ]
    for p in candidates:
        try:
            if p.exists():
                raw = p.read_bytes()
                import base64

                b64 = base64.b64encode(raw).decode('ascii')
                _WATERMARK_DATA_URL = f"data:image/png;base64,{b64}"
                return _WATERMARK_DATA_URL
        except Exception:
            continue

    # Fallback to static URL (works when collected/served by nginx)
    _WATERMARK_DATA_URL = '/static/validation/sikkim-logo.png'
    return _WATERMARK_DATA_URL
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
    payload_nonce = str(payload.get('nonce') or '').strip()
    if not source or not application_id:
        return Response({'detail': 'Invalid validation code.'}, status=status.HTTP_400_BAD_REQUEST)

    now_date = timezone.now().date()
    # Some production deployments (nginx) proxy only `/masters/...` to Django and serve `/` from Angular (SPA).
    # Expose the validation link under `/masters/v/<code>/` so it works without extra reverse-proxy routes.
    validation_pdf_url = request.build_absolute_uri('/masters/v/' + quote(token, safe=':') + '/')

    license_obj = None
    license_number = ''
    cat_code = None
    scat_code = None
    license_title = ''
    terms: list[str] = []

    if source == 'new_license_application':
        app = NewLicenseApplication.objects.filter(application_id=application_id).first()
        if not app:
            return Response({'detail': 'License not found.'}, status=status.HTTP_404_NOT_FOUND)

        license_obj = _resolve_license_obj(source, app.application_id, NewLicenseApplication)
        license_number = license_obj.license_id if license_obj else app.application_id
        cat_code = getattr(license_obj, 'license_category_id', None) if license_obj else getattr(app, 'license_category_id', None)
        scat_code = getattr(license_obj, 'license_sub_category_id', None) if license_obj else getattr(app, 'license_sub_category_id', None)
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
            'validFrom': _fmt_dt(license_obj.issue_date) if license_obj else _fmt_dt(getattr(app, 'created_at', None).date() if getattr(app, 'created_at', None) else None),
            'validTo': _fmt_dt(license_obj.valid_up_to) if license_obj else '',
            'generatedOn': _fmt_dt(now_date),
            'validationCode': token,
            'validationPdfUrl': validation_pdf_url,
            'validatedViaCode': False,
            'terms': terms,
        }

    elif source == 'license_application':
        app = LicenseApplication.objects.filter(application_id=application_id).first()
        if not app:
            return Response({'detail': 'License not found.'}, status=status.HTTP_404_NOT_FOUND)

        license_obj = _resolve_license_obj(source, app.application_id, LicenseApplication)
        if license_obj:
            license_number = license_obj.license_id
        elif getattr(app, 'license_no', None):
            license_number = str(app.license_no)
        else:
            license_number = app.application_id

        cat_code = getattr(license_obj, 'license_category_id', None) if license_obj else getattr(app, 'license_category_id', None)
        scat_code = getattr(license_obj, 'license_sub_category_id', None) if license_obj else None
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
            'validFrom': _fmt_dt(license_obj.issue_date) if license_obj else '',
            'validTo': _fmt_dt(license_obj.valid_up_to) if license_obj else (_fmt_dt(getattr(app, 'valid_up_to', None)) if getattr(app, 'valid_up_to', None) else ''),
            'generatedOn': _fmt_dt(now_date),
            'validationCode': token,
            'validationPdfUrl': validation_pdf_url,
            'validatedViaCode': False,
            'terms': terms,
        }

    else:
        return Response({'detail': 'Unsupported license source.'}, status=status.HTTP_400_BAD_REQUEST)

    if not license_obj:
        return Response({'detail': 'License not issued yet.'}, status=status.HTTP_403_FORBIDDEN)

    stored_nonce = str(getattr(license_obj, 'validation_nonce', '') or '').strip()
    if stored_nonce:
        if not payload_nonce or payload_nonce != stored_nonce:
            return Response({'detail': 'This is not the latest issued copy (superseded validation link).'}, status=status.HTTP_403_FORBIDDEN)
    elif payload_nonce:
        try:
            license_obj.validation_nonce = payload_nonce
            license_obj.validation_nonce_updated_at = timezone.now()
            license_obj.save(update_fields=['validation_nonce', 'validation_nonce_updated_at'])
            stored_nonce = payload_nonce
        except Exception:
            pass
    if not bool(getattr(license_obj, 'is_active', True)):
        return Response({'detail': 'License is not active.'}, status=status.HTTP_403_FORBIDDEN)
    if getattr(license_obj, 'issue_date', None) and license_obj.issue_date > now_date:
        return Response({'detail': 'License is not valid yet.'}, status=status.HTTP_403_FORBIDDEN)
    if getattr(license_obj, 'valid_up_to', None) and license_obj.valid_up_to < now_date:
        return Response({'detail': 'License has expired.'}, status=status.HTTP_403_FORBIDDEN)

    response_payload['validatedViaCode'] = True

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


def _build_validation_page(result: dict) -> str:
    status_code = str(result.get('status') or 'invalid')
    title = 'License Verification'

    badge_map = {
        'valid': ('VALID', '#0b7a0b', '#e6ffe6'),
        'expired': ('EXPIRED', '#a11', '#ffecec'),
        'inactive': ('INACTIVE', '#a11', '#ffecec'),
        'not_issued': ('NOT ISSUED', '#a11', '#ffecec'),
        'not_found': ('NOT FOUND', '#a11', '#ffecec'),
        'invalid_code': ('INVALID CODE', '#a11', '#ffecec'),
    }
    badge_text, badge_fg, badge_bg = badge_map.get(status_code, ('INVALID', '#a11', '#ffecec'))

    def esc(v) -> str:
        return html.escape(str(v or ''), quote=True)

    details = result.get('details') or {}
    download_url = result.get('downloadUrl') or ''
    can_download = bool(result.get('canDownload'))
    signature_verified = bool(result.get('signatureVerified'))
    is_current_copy = bool(result.get('isCurrentCopy', True))

    signature_text = 'SIGNATURE VERIFIED' if signature_verified else 'SIGNATURE NOT VERIFIED'
    signature_fg = '#0b7a0b' if signature_verified else '#a11'
    authenticity_text = str(result.get('authenticity') or ('Original (digitally signed QR)' if signature_verified else 'Unverified'))

    watermark_url = str(result.get('watermarkUrl') or '/static/validation/sikkim-logo.png')
    watermark_img = f"<img class='wm' alt='' src='{esc(watermark_url)}' />" if watermark_url else ''

    rows = [
        ('License Status', badge_text),
        ('QR Signature', 'VERIFIED' if signature_verified else 'NOT VERIFIED'),
        ('Original Copy', 'YES' if is_current_copy else 'NO'),
        ('Authenticity', authenticity_text),
        ('License No', details.get('licenseNumber')),
        ('License Title', details.get('licenseTitle')),
        ('Licensee Name', details.get('licenseeName')),
        ('Kind of Shop', details.get('kindOfShop')),
        ('Address', details.get('addressOfBusiness')),
        ('District', details.get('district')),
        ('Valid From', details.get('validFrom')),
        ('Valid To', details.get('validTo')),
        ('Application ID', details.get('applicationId')),
        ('Verification ID', result.get('verificationId')),
    ]
    rows_html = '\n'.join(
        [
            f"<div class='row'><div class='k'>{esc(k)}</div><div class='v'>{esc(v)}</div></div>"
            for k, v in rows
            if v
        ]
    )

    msg = esc(result.get('message') or '')
    code = esc(result.get('code') or '')
    scans = esc(result.get('scanCount') or '')

    btn_html = (
        f"<a class='btn' href='{esc(download_url)}'>Download Verification PDF</a>"
        if can_download and download_url
        else "<button class='btn btn-disabled' disabled>Verification PDF not available</button>"
    )

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{esc(title)}</title>
  <style>
    :root {{ --fg:#111; --muted:#666; --card:#fff; --bg:#f5f7fb; --border:#e5e7ef; }}
    body {{ margin:0; font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial; background:var(--bg); color:var(--fg); }}
    .wrap {{ max-width:860px; margin:24px auto; padding:0 16px; }}
    .card {{ position:relative; overflow:hidden; background:var(--card); border:1px solid var(--border); border-radius:14px; padding:18px; box-shadow:0 6px 18px rgba(0,0,0,.05); }}
    .wm {{ position:absolute; left:50%; top:52%; transform:translate(-50%,-50%); width:760px; max-width:160%; opacity:.28; pointer-events:none; user-select:none; filter:contrast(1.2); z-index:0; }}
    .card > :not(.wm) {{ position:relative; z-index:1; }}
    .top {{ display:flex; gap:12px; align-items:flex-start; justify-content:space-between; flex-wrap:wrap; }}
    h1 {{ font-size:18px; margin:0; }}
    .sub {{ margin-top:4px; font-size:13px; color:var(--muted); }}
    .badge {{ display:inline-block; padding:6px 10px; border-radius:999px; font-weight:700; font-size:12px; color:{badge_fg}; background:{badge_bg}; border:1px solid rgba(0,0,0,.08); }}
    .grid {{ margin-top:14px; display:grid; grid-template-columns:1fr; gap:8px; }}
    .row {{ display:flex; gap:12px; align-items:flex-start; padding:10px 12px; background:rgba(250,251,255,.72); border:1px solid var(--border); border-radius:12px; }}
    .k {{ width:160px; flex:0 0 160px; color:var(--muted); font-size:13px; }}
    .v {{ flex:1; font-size:13px; word-break:break-word; }}
    .actions {{ margin-top:14px; display:flex; gap:10px; flex-wrap:wrap; align-items:center; }}
    .btn {{ display:inline-block; padding:10px 14px; border-radius:12px; background:#0b5fff; color:#fff; text-decoration:none; font-weight:700; font-size:13px; border:0; }}
    .btn:active {{ transform:translateY(1px); }}
    .btn-disabled {{ background:#c9ceda; color:#3c4354; }}
    details {{ margin-top:14px; }}
    summary {{ cursor:pointer; color:#0b5fff; font-weight:700; }}
    code {{ display:block; padding:10px 12px; background:#0b1220; color:#e6edf3; border-radius:12px; overflow:auto; }}
    .foot {{ margin-top:14px; font-size:12px; color:var(--muted); }}
    .sig-pill {{ display:inline-block; padding:6px 10px; border-radius:999px; font-weight:800; font-size:12px; color:{signature_fg}; background:rgba(0,0,0,.04); border:1px solid rgba(0,0,0,.08); }}
    @media (max-width:520px) {{ .k {{ width:120px; flex-basis:120px; }} }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="card">
      {watermark_img}
      <div class="top">
        <div>
          <h1>Excise Department — Government of Sikkim</h1>
          <div class="sub">Public license verification</div>
        </div>
        <div style="display:flex; gap:10px; align-items:center; flex-wrap:wrap; justify-content:flex-end;">
          <div class="sig-pill">{esc(signature_text)}</div>
          <div class="badge">{esc(badge_text)}</div>
        </div>
      </div>

      <div class="grid">{rows_html}</div>

      <div class="actions">
        {btn_html}
        <div class="sub">{msg}{' · Scans today: ' + scans if scans else ''}</div>
      </div>

      <details>
        <summary>Show validation code</summary>
        <code>{code}</code>
      </details>

      <div class="foot">
        This page verifies whether the license is currently valid (active and within validity dates). If the license is not valid, the verification PDF download is disabled.
      </div>
    </div>
  </div>
</body>
</html>"""


def _resolve_validation_result(request, code: str) -> dict:
    token = _normalize_token(code)
    now_date = timezone.now().date()
    watermark_data_url = _get_watermark_data_url()

    try:
        payload = signing.loads(token, salt='final-license')
    except Exception:
        return {
            'status': 'invalid_code',
            'message': 'Invalid validation code.',
            'code': token,
            'signatureVerified': False,
            'authenticity': 'Unverified (QR code is not digitally signed)',
            'canDownload': False,
            'details': {},
            'verificationId': hashlib.sha256(token.encode('utf-8')).hexdigest()[:12] if token else '',
            'watermarkUrl': watermark_data_url,
        }

    if not isinstance(payload, dict):
        return {
            'status': 'invalid_code',
            'message': 'Invalid validation code.',
            'code': token,
            'signatureVerified': False,
            'authenticity': 'Unverified (QR code is not digitally signed)',
            'canDownload': False,
            'details': {},
            'verificationId': hashlib.sha256(token.encode('utf-8')).hexdigest()[:12] if token else '',
            'watermarkUrl': watermark_data_url,
        }

    source = str(payload.get('source') or '').strip()
    application_id = str(payload.get('applicationId') or '').strip()
    payload_nonce = str(payload.get('nonce') or '').strip()
    if not source or not application_id:
        return {
            'status': 'invalid_code',
            'message': 'Invalid validation code.',
            'code': token,
            'signatureVerified': False,
            'authenticity': 'Unverified (QR code is not digitally signed)',
            'canDownload': False,
            'details': {},
            'verificationId': hashlib.sha256(token.encode('utf-8')).hexdigest()[:12] if token else '',
            'watermarkUrl': watermark_data_url,
        }

    details: dict = {
        'applicationId': application_id,
        'licenseTitle': '',
        'licenseNumber': '',
        'licenseeName': '',
        'kindOfShop': '',
        'addressOfBusiness': '',
        'district': '',
        'validFrom': '',
        'validTo': '',
    }

    license_obj = None
    app = None
    is_current_copy = True
    if source == 'new_license_application':
        app = NewLicenseApplication.objects.filter(application_id=application_id).first()
        if not app:
            return {
                'status': 'not_found',
                'message': 'License not found.',
                'code': token,
                'signatureVerified': True,
                'authenticity': 'Digitally signed QR (record not found)',
                'canDownload': False,
                'details': details,
                'verificationId': hashlib.sha256(token.encode('utf-8')).hexdigest()[:12],
                'watermarkUrl': watermark_data_url,
            }
        license_obj = _resolve_license_obj(source, app.application_id, NewLicenseApplication)
        cat_code = getattr(license_obj, 'license_category_id', None) if license_obj else getattr(app, 'license_category_id', None)
        scat_code = getattr(license_obj, 'license_sub_category_id', None) if license_obj else getattr(app, 'license_sub_category_id', None)
        license_title, _terms = _fetch_title_terms(cat_code, scat_code)
        details.update(
            {
                'licenseTitle': license_title,
                'licenseNumber': (license_obj.license_id if license_obj else app.application_id),
                'licenseeName': getattr(app, 'applicant_name', '') or '',
                'kindOfShop': app.license_type.license_type if getattr(app, 'license_type', None) else '',
                'addressOfBusiness': _build_address_from_application(app),
                'district': app.site_district.district if getattr(app, 'site_district', None) else '',
                'validFrom': _fmt_dt(license_obj.issue_date) if license_obj else _fmt_dt(getattr(app, 'created_at', None).date() if getattr(app, 'created_at', None) else None),
                'validTo': _fmt_dt(license_obj.valid_up_to) if license_obj else '',
            }
        )
    elif source == 'license_application':
        app = LicenseApplication.objects.filter(application_id=application_id).first()
        if not app:
            return {
                'status': 'not_found',
                'message': 'License not found.',
                'code': token,
                'signatureVerified': True,
                'authenticity': 'Digitally signed QR (record not found)',
                'canDownload': False,
                'details': details,
                'verificationId': hashlib.sha256(token.encode('utf-8')).hexdigest()[:12],
                'watermarkUrl': watermark_data_url,
            }
        license_obj = _resolve_license_obj(source, app.application_id, LicenseApplication)
        cat_code = getattr(license_obj, 'license_category_id', None) if license_obj else getattr(app, 'license_category_id', None)
        scat_code = getattr(license_obj, 'license_sub_category_id', None) if license_obj else None
        license_title, _terms = _fetch_title_terms(cat_code, scat_code)
        license_number = (
            license_obj.license_id
            if license_obj
            else (str(app.license_no) if getattr(app, 'license_no', None) else app.application_id)
        )
        details.update(
            {
                'licenseTitle': license_title,
                'licenseNumber': license_number,
                'licenseeName': (getattr(app, 'member_name', None) or getattr(app, 'establishment_name', None) or ''),
                'kindOfShop': app.license_type.license_type if getattr(app, 'license_type', None) else '',
                'addressOfBusiness': _build_address_from_application(app),
                'district': app.excise_district.district if getattr(app, 'excise_district', None) else '',
                'validFrom': _fmt_dt(license_obj.issue_date) if license_obj else '',
                'validTo': _fmt_dt(license_obj.valid_up_to) if license_obj else (_fmt_dt(getattr(app, 'valid_up_to', None)) if getattr(app, 'valid_up_to', None) else ''),
            }
        )
    else:
        return {
            'status': 'invalid_code',
            'message': 'Unsupported license source.',
            'code': token,
            'signatureVerified': True,
            'authenticity': 'Digitally signed QR (unsupported source)',
            'canDownload': False,
            'details': details,
            'verificationId': hashlib.sha256(token.encode('utf-8')).hexdigest()[:12],
            'watermarkUrl': watermark_data_url,
        }

    status_code = 'valid'
    message = 'License is valid.'
    can_download = True
    authenticity = 'Original (digitally signed QR)'

    stored_nonce = str(getattr(license_obj, 'validation_nonce', '') or '').strip() if license_obj else ''
    if stored_nonce:
        if not payload_nonce or payload_nonce != stored_nonce:
            is_current_copy = False
            can_download = False
            authenticity = 'Digitally signed QR (superseded copy)'
            message = 'This is not the latest issued copy (superseded validation link).'
    elif payload_nonce and license_obj:
        try:
            license_obj.validation_nonce = payload_nonce
            license_obj.validation_nonce_updated_at = timezone.now()
            license_obj.save(update_fields=['validation_nonce', 'validation_nonce_updated_at'])
            stored_nonce = payload_nonce
        except Exception:
            pass

    if not license_obj:
        status_code = 'not_issued'
        if is_current_copy:
            message = 'License not issued yet.'
        can_download = False
        authenticity = 'Digitally signed QR (license not issued)'
    elif not bool(getattr(license_obj, 'is_active', True)):
        status_code = 'inactive'
        if is_current_copy:
            message = 'License is not active.'
        can_download = False
        authenticity = 'Digitally signed QR (license inactive)'
    elif getattr(license_obj, 'issue_date', None) and license_obj.issue_date > now_date:
        status_code = 'inactive'
        if is_current_copy:
            message = 'License is not valid yet.'
        can_download = False
        authenticity = 'Digitally signed QR (not valid yet)'
    elif getattr(license_obj, 'valid_up_to', None) and license_obj.valid_up_to < now_date:
        status_code = 'expired'
        if is_current_copy:
            message = 'License has expired.'
        can_download = False
        authenticity = 'Digitally signed QR (license expired)'

    download_url = ''
    if can_download:
        # keep original URL shape; add query param to trigger file download.
        download_url = request.build_absolute_uri(request.path + '?download=1')

    token_hash = hashlib.sha256(token.encode('utf-8')).hexdigest() if token else ''
    scan_key = f'public_validation:scan:{token_hash}:{now_date.isoformat()}'
    scan_count = None
    try:
        scan_count = cache.incr(scan_key)
    except Exception:
        try:
            cache.set(scan_key, 1, timeout=24 * 60 * 60)
            scan_count = 1
        except Exception:
            scan_count = None

    return {
        'status': status_code,
        'message': message,
        'code': token,
        'signatureVerified': True,
        'authenticity': authenticity,
        'isCurrentCopy': is_current_copy,
        'canDownload': can_download,
        'downloadUrl': download_url,
        'details': details,
        'verificationId': token_hash[:12] if token_hash else '',
        'scanCount': scan_count,
        'watermarkUrl': watermark_data_url,
    }


@require_GET
def validate_license_landing(request, code: str):
    """
    Public, QR-friendly landing page.

    - GET /v/<code>/            -> human-friendly verification page
    - GET /v/<code>/?download=1 -> downloads verification PDF only if currently valid
    """
    if str(request.GET.get('download') or '').strip() in {'1', 'true', 'yes'}:
        # Use the existing PDF generator but enforce validity checks.
        resp = _validate_license_pdf_from_code(request, code)
        # _validate_license_pdf_from_code returns DRF Response on errors; convert to HTML.
        if isinstance(resp, Response):
            result = _resolve_validation_result(request, code)
            result['canDownload'] = False
            result['downloadUrl'] = ''
            html_body = _build_validation_page(result)
            return HttpResponse(html_body, content_type='text/html; charset=utf-8', status=int(resp.status_code))
        return resp

    result = _resolve_validation_result(request, code)
    html_body = _build_validation_page(result)
    return HttpResponse(html_body, content_type='text/html; charset=utf-8')

