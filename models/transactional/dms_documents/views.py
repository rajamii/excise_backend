import io
import re
import logging
from pathlib import Path
from urllib.parse import unquote
from django.http import FileResponse, Http404
from django.views.decorators.clickjacking import xframe_options_exempt
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from utils.dms_service import dms_client
from .models import DMSUploadedDocument, DMSDocumentCompany, DMSDocumentLabel, DMSTemporaryUpload

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


@api_view(['POST'])
@permission_classes([AllowAny])
@parser_classes([MultiPartParser, FormParser, JSONParser])
def upload_temporary_document(request):
    """
    Temporarily stores an uploaded document in MongoDB GridFS and PostgreSQL (dms_temperary_uploads).
    Allows applicant to step away or return later before final submit.
    """
    file_obj = request.FILES.get('file') or request.FILES.get('document')
    if not file_obj:
        for k in request.FILES:
            file_obj = request.FILES[k]
            break

    if not file_obj:
        return Response({'success': False, 'error': 'No file was provided in the request.'}, status=status.HTTP_400_BAD_REQUEST)

    app_type = (
        request.data.get('application_type') or 
        request.data.get('module') or 
        request.data.get('arn') or 
        'general'
    ).strip().lower()

    doc_field = (
        request.data.get('document_field') or 
        request.data.get('document_id') or 
        request.data.get('doc_id') or 
        request.data.get('field_name') or 
        'document'
    ).strip()

    username = (
        request.data.get('username') or 
        request.data.get('user_id') or 
        request.data.get('beneficiary_mobile')
    )
    if not username and request.user and request.user.is_authenticated:
        username = request.user.username
    if not username:
        username = 'anonymous'

    result = dms_client.save_temporary_upload(
        username=str(username),
        application_type=app_type,
        document_field=doc_field,
        file_obj=file_obj,
        user=request.user if request.user.is_authenticated else None
    )

    if result.get('success'):
        return Response(result, status=status.HTTP_201_CREATED)
    else:
        return Response(result, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
@permission_classes([AllowAny])
def list_temporary_documents(request):
    """
    Lists all temporary draft documents for the current user and/or module.
    """
    username = request.GET.get('username') or request.GET.get('user_id')
    if not username and request.user and request.user.is_authenticated:
        username = request.user.username

    app_type = request.GET.get('application_type') or request.GET.get('module')

    docs = dms_client.list_temporary_uploads(username=username, application_type=app_type)
    if not docs and (not username or username.lower() in ('anon', 'anonymous')):
        # Fallback to general/module temporary uploads if no specific user records
        docs = dms_client.list_temporary_uploads(username=None, application_type=app_type)

    return Response({'success': True, 'count': len(docs), 'documents': docs})


@api_view(['GET'])
@permission_classes([AllowAny])
@xframe_options_exempt
def download_temporary_document(request, application_type, document_field):
    """
    Streams a temporary document stored in dms_temperary_uploads / MongoDB GridFS.
    """
    clean_app_type = str(application_type).strip().lower()
    clean_field = str(document_field).strip()

    username = request.GET.get('username') or request.GET.get('user_id')
    if not username and request.user and request.user.is_authenticated:
        username = request.user.username

    candidates = dms_client._get_field_candidates(clean_field)
    qs = DMSTemporaryUpload.objects.filter(
        application_type=clean_app_type,
        document_field__in=candidates
    )
    if username:
        qs = qs.filter(username__iexact=username)

    temp_rec = qs.order_by('-updated_at').first()
    if not temp_rec:
        temp_rec = DMSTemporaryUpload.objects.filter(
            application_type=clean_app_type,
            document_field__iexact=clean_field
        ).first()

    if not temp_rec:
        raise Http404(f"Temporary document '{clean_field}' not found for module '{clean_app_type}'.")

    content = None
    filename = temp_rec.original_filename or f"{clean_field}.pdf"
    mime_type = temp_rec.mime_type or "application/pdf"

    if temp_rec.dms_reference:
        content, fn, mime = dms_client.download_document(temp_rec.dms_reference, temp_rec.storage_type)
        if fn:
            filename = fn
        if mime:
            mime_type = mime

    if not content and temp_rec.file:
        try:
            temp_rec.file.open('rb')
            content = temp_rec.file.read()
        except Exception as read_err:
            logger.error("Failed reading file from storage: %s", read_err)

    if not content:
        raise Http404(f"Could not retrieve temporary document bytes for '{clean_field}'.")

    ext = Path(filename).suffix
    if not ext:
        if 'pdf' in mime_type:
            ext = '.pdf'
        elif 'png' in mime_type:
            ext = '.png'
        elif 'jpeg' in mime_type or 'jpg' in mime_type:
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


@api_view(['DELETE', 'POST'])
@permission_classes([AllowAny])
def delete_temporary_document(request, application_type=None, document_field=None):
    """
    Deletes a temporary document from dms_temperary_uploads and MongoDB GridFS.
    """
    app_type = application_type or request.data.get('application_type') or request.GET.get('application_type')
    doc_field = document_field or request.data.get('document_field') or request.data.get('document_id') or request.GET.get('document_field')

    username = (
        request.data.get('username') or 
        request.GET.get('username') or 
        request.data.get('user_id') or 
        (request.user.username if request.user and request.user.is_authenticated else None)
    )

    if not app_type or not doc_field:
        return Response({'success': False, 'error': 'Both application_type and document_field are required.'}, status=status.HTTP_400_BAD_REQUEST)

    if not username:
        temp_rec = DMSTemporaryUpload.objects.filter(
            application_type=str(app_type).strip().lower(),
            document_field=str(doc_field).strip()
        ).first()
        if temp_rec:
            username = temp_rec.username
        else:
            return Response({'success': False, 'error': 'Document not found.'}, status=status.HTTP_404_NOT_FOUND)

    deleted = dms_client.delete_temporary_upload(
        username=username,
        application_type=app_type,
        document_field=doc_field
    )

    if deleted:
        return Response({'success': True, 'msg': f"Document '{doc_field}' successfully deleted from temporary uploads."})
    else:
        return Response({'success': False, 'error': f"Document '{doc_field}' could not be deleted or not found."}, status=status.HTTP_404_NOT_FOUND)

