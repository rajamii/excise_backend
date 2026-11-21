import io
import re
import logging
from pathlib import Path
from urllib.parse import unquote
from django.http import FileResponse, Http404
from django.views.decorators.clickjacking import xframe_options_exempt
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from utils.dms_service import dms_client
from .models import DMSUploadedDocument, DMSDocumentCompany, DMSDocumentLabel

logger = logging.getLogger(__name__)


@api_view(['GET'])
@permission_classes([AllowAny])
@xframe_options_exempt
def download_universal_dms_document(request, application_id, document_field):
    """
    Universal document viewer/downloader for ANY module in SEMS.
    Queries:
    - dms_document_label for label registration applications ('LBL/...')
    - dms_document_company for company applications ('COMP/...', 'CCOL/...')
    - dms_uploaded_document_new for new license / salesman-barman applications ('NLI/...', 'SBM/...')
    """
    clean_app_id = unquote(application_id).strip().rstrip('/')
    raw_field = str(document_field).strip()
    clean_field = raw_field.lower()

    app_id_lower = clean_app_id.lower()
    if 'lbl' in app_id_lower:
        models_to_check = [DMSDocumentLabel, DMSDocumentCompany, DMSUploadedDocument]
    elif 'comp' in app_id_lower or 'ccol' in app_id_lower:
        models_to_check = [DMSDocumentCompany, DMSDocumentLabel, DMSUploadedDocument]
    else:
        models_to_check = [DMSUploadedDocument, DMSDocumentCompany, DMSDocumentLabel]

    candidates = [
        raw_field,
        clean_field,
        re.sub(r'(?<!^)(?=[A-Z])', '_', raw_field).lower(),
        re.sub(r'_([a-z])', lambda m: m.group(1).upper(), raw_field)
    ]

    def _lookup(model_cls, app_id):
        rec = model_cls.objects.filter(application_id=app_id, document_field__in=candidates).first()
        if not rec:
            rec = model_cls.objects.filter(application_id=app_id, document_field__iexact=raw_field).first()
        if not rec and '/' in app_id:
            parts = app_id.split('/', 1)
            rec = model_cls.objects.filter(application_id=parts[1], document_field__in=candidates).first()
        if not rec:
            rec = model_cls.objects.filter(application_id__iexact=app_id, document_field__in=candidates).first()
        return rec

    doc_record = None
    for model_cls in models_to_check:
        doc_record = _lookup(model_cls, clean_app_id)
        if doc_record:
            break

    if not doc_record:
        raise Http404(f"Document '{clean_field}' not found for application '{clean_app_id}'.")

    content, filename, mime_type = dms_client.download_document(
        doc_record.dms_reference,
        doc_record.storage_type,
        doc_record.application_id
    )

    if not content:
        raise Http404(f"Could not retrieve document bytes for '{clean_field}'.")

    # Ensure safe extension for browser recognition
    ext = Path(doc_record.original_filename or filename).suffix
    if not ext:
        if 'pdf' in (mime_type or ''):
            ext = '.pdf'
        elif 'png' in (mime_type or ''):
            ext = '.png'
        elif 'jpeg' in (mime_type or '') or 'jpg' in (mime_type or ''):
            ext = '.jpg'
        else:
            ext = '.bin'
    safe_filename = f"{clean_field}{ext}"

    response = FileResponse(io.BytesIO(content), content_type=mime_type or 'application/octet-stream')
    response['Content-Disposition'] = f'inline; filename="{safe_filename}"'
    response['Content-Length'] = len(content)
    response['Accept-Ranges'] = 'bytes'
    response['Access-Control-Allow-Origin'] = '*'
    return response
