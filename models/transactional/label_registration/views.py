import json
import logging
import io
import re
from datetime import date
from pathlib import Path
from urllib.parse import unquote

from django.db import transaction
from django.db.models import Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from auth.workflow.models import Workflow
from auth.workflow.permissions import HasStagePermission
from auth.workflow.services import WorkflowService
from models.transactional.dashboard_cache import dashboard_counts_cache
from utils.dms_service import dms_client
from utils.file_validation import validate_uploaded_file
from .models import LabelRegistration, LabelRegistrationDocument
from .serializers import LabelRegistrationSerializer

logger = logging.getLogger(__name__)

LABEL_REGISTRATION_DMS_FIELDS = [
    'renewed_licence_copy',
    'registered_partnership_deed',
    'article_of_association',
    'memorandum_of_association',
    'trade_mark_registration',
    'certificate_of_registration',
    'cost_chart',
    'undertaking',
    'product_photo',
]


def _process_label_registration_dms_uploads(application, request_files, user=None, upload_details=None):
    """
    Uploads all label registration documents to MongoDB GridFS / DMS,
    signs them with AES-256 / HMAC-SHA256, and tracks them in DMSDocumentLabel (dms_document_label).
    """
    user_identifier = getattr(user, 'username', str(getattr(user, 'id', 'system')))
    mobile_number = ""
    lic_details = getattr(application, 'licensee_details', {}) or {}
    if isinstance(lic_details, dict):
        mobile_number = str(lic_details.get('mobileNumber') or lic_details.get('mobile_number') or '')

    alias_map = {
        'renewedLicenceCopy': 'renewed_licence_copy',
        'registeredPartnershipDeed': 'registered_partnership_deed',
        'articleOfAssociation': 'article_of_association',
        'memorandumOfAssociation': 'memorandum_of_association',
        'tradeMarkRegistration': 'trade_mark_registration',
        'certificateOfRegistration': 'certificate_of_registration',
        'costChart': 'cost_chart',
        'undertaking': 'undertaking',
        'productPhoto': 'product_photo',
    }

    processed_fields = set()

    for raw_key, file_obj in request_files.items():
        if not file_obj or not getattr(file_obj, 'size', 0):
            continue
        canonical_field = alias_map.get(raw_key, raw_key)
        processed_fields.add(canonical_field)
        try:
            validate_uploaded_file(file_obj, max_size_bytes=10 * 1024 * 1024, field_label=canonical_field)
            doc_title = _document_name(upload_details, canonical_field) if upload_details else getattr(file_obj, 'name', canonical_field)
            upload_result = dms_client.upload_document(
                file_obj=file_obj,
                document_field=canonical_field,
                application_id=str(application.application_id),
                user_id=user_identifier,
                mobile=mobile_number,
                doc_type_name=doc_title
            )

            if upload_result.get('success'):
                dms_client.record_document(
                    application_type='label_registration',
                    application_id=str(application.application_id),
                    document_field=canonical_field,
                    upload_result=upload_result,
                    original_filename=getattr(file_obj, 'name', ''),
                    file_size=getattr(file_obj, 'size', 0),
                    mime_type=upload_result.get('mime_type', '')
                )
                logger.info("DMS Upload: %s (%s) saved to MongoDB GridFS %s in dms_document_label",
                            canonical_field, application.application_id, upload_result.get('dms_reference'))
            else:
                logger.warning("DMS upload failed for %s: %s", canonical_field, upload_result.get('error'))
        except Exception as exc:
            logger.error("Error processing DMS upload for %s on label application %s: %s",
                         canonical_field, application.application_id, exc)

    for target_field in LABEL_REGISTRATION_DMS_FIELDS:
        if target_field in processed_fields:
            continue
        file_obj = request_files.get(target_field)
        if not file_obj:
            for camel, snake in alias_map.items():
                if snake == target_field:
                    file_obj = request_files.get(camel)
                    if file_obj:
                        break
        if not file_obj or not getattr(file_obj, 'size', 0):
            continue

        try:
            validate_uploaded_file(file_obj, max_size_bytes=10 * 1024 * 1024, field_label=target_field)
            doc_title = _document_name(upload_details, target_field) if upload_details else getattr(file_obj, 'name', target_field)
            upload_result = dms_client.upload_document(
                file_obj=file_obj,
                document_field=target_field,
                application_id=str(application.application_id),
                user_id=user_identifier,
                mobile=mobile_number,
                doc_type_name=doc_title
            )

            if upload_result.get('success'):
                dms_client.record_document(
                    application_type='label_registration',
                    application_id=str(application.application_id),
                    document_field=target_field,
                    upload_result=upload_result,
                    original_filename=getattr(file_obj, 'name', ''),
                    file_size=getattr(file_obj, 'size', 0),
                    mime_type=upload_result.get('mime_type', '')
                )
                logger.info("DMS Upload: %s (%s) saved to MongoDB GridFS %s in dms_document_label",
                            target_field, application.application_id, upload_result.get('dms_reference'))
            else:
                logger.warning("DMS upload failed for %s: %s", target_field, upload_result.get('error'))
        except Exception as exc:
            logger.error("Error processing DMS upload for %s on label application %s: %s",
                         target_field, application.application_id, exc)


STAGE_APPLICANT_APPLIED = 'applicant_applied'
STAGE_PERMIT_SECTION = 'permit_section'
STAGE_PERMIT_SECTION_OBJECTION = 'permit_section_objection'
STAGE_DEPUTY_COMMISSIONER = 'deputy_commissioner'
STAGE_DEPUTY_COMMISSIONER_OBJECTION = 'deputy_commissioner_objection'
STAGE_COMMISSIONER = 'commissioner'
STAGE_COMMISSIONER_OBJECTION = 'commissioner_objection'
STAGE_APPROVED = 'approved'
STAGE_REJECTED = 'rejected'

OFFICER_PENDING_STAGES = [
    STAGE_PERMIT_SECTION,
    STAGE_DEPUTY_COMMISSIONER,
    STAGE_COMMISSIONER,
]

OBJECTION_STAGES = [
    STAGE_PERMIT_SECTION_OBJECTION,
    STAGE_DEPUTY_COMMISSIONER_OBJECTION,
    STAGE_COMMISSIONER_OBJECTION,
]

ROLE_STAGE_MAP = {
    'permit_section': {
        'pending': [STAGE_PERMIT_SECTION, STAGE_PERMIT_SECTION_OBJECTION],
        'approved': [STAGE_DEPUTY_COMMISSIONER],
        'rejected': [STAGE_REJECTED],
    },
    'deputy_commissioner': {
        'pending': [STAGE_DEPUTY_COMMISSIONER, STAGE_DEPUTY_COMMISSIONER_OBJECTION],
        'approved': [STAGE_COMMISSIONER],
        'rejected': [STAGE_REJECTED],
    },
    'commissioner': {
        'pending': [STAGE_COMMISSIONER, STAGE_COMMISSIONER_OBJECTION],
        'approved': [STAGE_APPROVED],
        'rejected': [STAGE_REJECTED],
    },
}


def _parse_json_payload(raw: str | None, *, field_name: str, default):
    if raw is None or raw == '':
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in '{field_name}'.") from exc


def _parse_iso_date(raw: str | None) -> date:
    if not raw:
        return timezone.now().date()
    try:
        return date.fromisoformat(str(raw))
    except ValueError:
        return timezone.now().date()


def _normalize_role(role_name):
    if not role_name:
        return None
    normalized = str(role_name).strip().lower().replace('-', '_').replace(' ', '_')
    aliases = {
        'license_user': 'licensee',
        'licensee_user': 'licensee',
        'distributor': 'licensee',
        'singlewindow': 'single_window',
        'siteadmin': 'site_admin',
        'permitsection': 'permit_section',
        'permit_excise': 'permit_section',
        'permitexcise': 'permit_section',
        'permit_excise_section': 'permit_section',
        'permit_excise_officer': 'permit_section',
        'deputycommissioner': 'deputy_commissioner',
        'deputy_commissioner_excise': 'deputy_commissioner',
        'deputycommissionerexcise': 'deputy_commissioner',
        'joint_commissioner': 'deputy_commissioner',
        'jointcommissioner': 'deputy_commissioner',
        'commissioner_excise': 'commissioner',
        'commissionerexcise': 'commissioner',
    }
    return aliases.get(normalized, normalized)


def _resolve_workflow() -> Workflow:
    workflow = Workflow.objects.filter(name='Label Registration').first()
    if not workflow:
        raise Http404(
            "Workflow 'Label Registration' not found. "
            "Run migrations or create it in the Django admin before accepting applications."
        )
    return workflow


def _document_name(upload_details, key):
    for item in (upload_details or {}).get('documents', []):
        if item.get('key') == key:
            return item.get('name') or key
    return key


def _base_queryset():
    return LabelRegistration.objects.select_related(
        'workflow',
        'current_stage',
        'applicant',
    ).prefetch_related(
        'documents',
        'transactions',
        'objections',
    )


def _filter_by_role(request):
    role = _normalize_role(request.user.role.name if getattr(request.user, 'role', None) else None)
    queryset = _base_queryset()

    if role in ['single_window', 'site_admin']:
        return queryset
    if role == 'licensee':
        return queryset.filter(applicant=request.user)

    stages = ROLE_STAGE_MAP.get(role, {})
    officer_stages = stages.get('pending', []) + stages.get('approved', []) + stages.get('rejected', [])
    if officer_stages:
        return queryset.filter(current_stage__name__in=officer_stages).distinct()
    return queryset.none()


@api_view(['POST'])
@parser_classes([MultiPartParser, FormParser, JSONParser])
@permission_classes([HasStagePermission])
def apply_label_registration(request):
    try:
        licensee_details = _parse_json_payload(
            request.data.get('licensee_details'), field_name='licensee_details', default={}
        )
        product_details = _parse_json_payload(
            request.data.get('product_details'), field_name='product_details', default={}
        )
        packaging_details = _parse_json_payload(
            request.data.get('packaging_details'), field_name='packaging_details', default={}
        )
        upload_details = _parse_json_payload(
            request.data.get('upload_details'), field_name='upload_details', default={'documents': []}
        )
    except ValueError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    application_date = _parse_iso_date(request.data.get('application_date'))
    prefix = f"LBL/{application_date.strftime('%Y%m%d')}"

    try:
        with transaction.atomic():
            workflow = _resolve_workflow()
            initial_stage = workflow.stages.filter(is_initial=True).first()
            if not initial_stage:
                return Response(
                    {'detail': 'Workflow "Label Registration" has no initial stage (is_initial=True).'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            last_app = (
                LabelRegistration.objects.filter(application_id__startswith=prefix)
                .select_for_update()
                .order_by('-application_id')
                .first()
            )
            last_number = int(last_app.application_id.split('/')[-1]) if last_app else 0
            application_id = f"{prefix}/{str(last_number + 1).zfill(4)}"

            application = LabelRegistration.objects.create(
                application_id=application_id,
                workflow=workflow,
                current_stage=initial_stage,
                applicant=request.user,
                status='Submitted',
                application_date=application_date,
                licensee_details=licensee_details,
                product_details=product_details,
                packaging_details=packaging_details,
                upload_details=upload_details,
            )

            for key, uploaded_file in request.FILES.items():
                LabelRegistrationDocument.objects.update_or_create(
                    application=application,
                    document_key=key,
                    defaults={
                        'document_name': _document_name(upload_details, key),
                        'file': uploaded_file,
                        'mime_type': getattr(uploaded_file, 'content_type', '') or '',
                    },
                )

            WorkflowService.submit_application(
                application=application,
                user=request.user,
                remarks='Label registration application submitted',
            )

            # Process DMS uploads to MongoDB GridFS & record into dms_document_label
            try:
                _process_label_registration_dms_uploads(application, request.FILES, user=request.user, upload_details=upload_details)
            except Exception as dms_err:
                logger.warning("DMS upload failed during label registration creation: %s", dms_err)
    except Http404 as exc:
        return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as exc:
        return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    fresh = _base_queryset().get(pk=application.pk)
    return Response(LabelRegistrationSerializer(fresh).data, status=status.HTTP_201_CREATED)


@api_view(['GET'])
@permission_classes([HasStagePermission])
def list_label_registrations(request):
    return Response(LabelRegistrationSerializer(_filter_by_role(request), many=True).data)


@api_view(['GET'])
@permission_classes([HasStagePermission])
def label_registration_detail(request, application_id):
    application = get_object_or_404(_filter_by_role(request), application_id=application_id)
    return Response(LabelRegistrationSerializer(application).data)


@api_view(['GET'])
@permission_classes([IsAuthenticated, HasStagePermission])
@dashboard_counts_cache("label_registration:counts")
def dashboard_counts(request):
    if not request.user or not getattr(request.user, "is_authenticated", False):
        return Response({"detail": "Authentication credentials were not provided."}, status=status.HTTP_401_UNAUTHORIZED)
    role = _normalize_role(getattr(getattr(request.user, 'role', None), 'name', None))
    base_qs = LabelRegistration.objects

    if role in ROLE_STAGE_MAP:
        stages = ROLE_STAGE_MAP[role]
        counts = {
            'pending': base_qs.filter(current_stage__name__in=stages['pending']).count(),
            'approved': base_qs.filter(current_stage__name__in=stages['approved']).count(),
            'objection': base_qs.filter(current_stage__name__in=OBJECTION_STAGES).count(),
            'rejected': base_qs.filter(current_stage__name__in=stages['rejected']).count(),
        }
    elif role == 'licensee':
        mine = base_qs.filter(applicant=request.user)
        counts = {
            'applied': mine.filter(current_stage__name__in=OFFICER_PENDING_STAGES).count(),
            'pending': 0,
            'objection': mine.filter(current_stage__name__in=OBJECTION_STAGES).count(),
            'approved': mine.filter(current_stage__name=STAGE_APPROVED, is_approved=True).count(),
            'rejected': mine.filter(current_stage__name=STAGE_REJECTED).count(),
        }
    elif role in ['site_admin', 'single_window', 'secretary', 'commissioner', 'joint_commissioner', 'executive']:
        counts = {
            'total': base_qs.count(),
            'applied': base_qs.filter(current_stage__name=STAGE_APPLICANT_APPLIED).count(),
            'pending': base_qs.filter(current_stage__name__in=OFFICER_PENDING_STAGES).count(),
            'in_review': base_qs.filter(current_stage__name__in=OFFICER_PENDING_STAGES).count(),
            'objection': base_qs.filter(current_stage__name__in=OBJECTION_STAGES).count(),
            'approved': base_qs.filter(current_stage__name=STAGE_APPROVED, is_approved=True).count(),
            'rejected': base_qs.filter(current_stage__name=STAGE_REJECTED).count(),
        }
    else:
        counts = {'applied': 0, 'pending': 0, 'objection': 0, 'approved': 0, 'rejected': 0}

    return Response(counts)


@api_view(['GET'])
@parser_classes([JSONParser])
@permission_classes([HasStagePermission])
@dashboard_counts_cache("label_registration:list")
def application_group(request):
    role = _normalize_role(request.user.role.name if getattr(request.user, 'role', None) else None)
    base_qs = _filter_by_role(request)

    def _serialize(qs):
        return LabelRegistrationSerializer(qs, many=True).data

    if role in ROLE_STAGE_MAP:
        stages = ROLE_STAGE_MAP[role]
        return Response({
            'pending': _serialize(base_qs.filter(current_stage__name__in=stages['pending'])),
            'approved': _serialize(base_qs.filter(current_stage__name__in=stages['approved'])),
            'objection': _serialize(base_qs.filter(current_stage__name__in=OBJECTION_STAGES)),
            'rejected': _serialize(base_qs.filter(current_stage__name__in=stages['rejected'])),
        })

    if role == 'licensee':
        return Response({
            'applied': _serialize(base_qs.filter(current_stage__name__in=OFFICER_PENDING_STAGES)),
            'pending': [],
            'objection': _serialize(base_qs.filter(current_stage__name__in=OBJECTION_STAGES)),
            'approved': _serialize(base_qs.filter(current_stage__name=STAGE_APPROVED)),
            'rejected': _serialize(base_qs.filter(current_stage__name=STAGE_REJECTED)),
        })

    return Response({
        'applied': _serialize(base_qs.filter(current_stage__name=STAGE_APPLICANT_APPLIED)),
        'pending': _serialize(base_qs.filter(current_stage__name__in=OFFICER_PENDING_STAGES)),
        'in_review': _serialize(base_qs.filter(current_stage__name__in=OFFICER_PENDING_STAGES)),
        'objection': _serialize(base_qs.filter(current_stage__name__in=OBJECTION_STAGES)),
        'approved': _serialize(base_qs.filter(current_stage__name=STAGE_APPROVED)),
        'rejected': _serialize(base_qs.filter(current_stage__name=STAGE_REJECTED)),
    })


from django.views.decorators.clickjacking import xframe_options_exempt


@api_view(['GET'])
@permission_classes([AllowAny])
@xframe_options_exempt
def download_label_document(request, application_id, document_field):
    """
    Downloads or streams an uploaded label registration document by field name.
    Retrieves from MongoDB GridFS or local storage.
    """
    clean_app_id = unquote(application_id).strip().rstrip('/')
    clean_field = str(document_field).strip().lower()

    app = LabelRegistration.objects.filter(
        Q(application_id=clean_app_id) |
        Q(application_id=unquote(clean_app_id)) |
        Q(application_id=clean_app_id.replace('/', '_'))
    ).first()

    if not app:
        raise Http404(f"Label registration application '{clean_app_id}' not found.")

    from models.transactional.dms_documents.models import DMSDocumentLabel
    raw_field = str(document_field).strip()
    candidates = [
        raw_field,
        clean_field,
        clean_field.replace('_', ''),
        re.sub(r'(?<!^)(?=[A-Z])', '_', raw_field).lower(),
        re.sub(r'_([a-z])', lambda m: m.group(1).upper(), clean_field)
    ]

    doc_record = DMSDocumentLabel.objects.filter(
        application_id=app.application_id,
        document_field__in=candidates
    ).first()

    if not doc_record:
        # Fallback to LabelRegistrationDocument if exists
        lbl_doc = LabelRegistrationDocument.objects.filter(
            application=app,
            document_key__in=candidates
        ).first()
        if lbl_doc and lbl_doc.file and hasattr(lbl_doc.file, 'path') and Path(lbl_doc.file.path).is_file():
            import mimetypes
            guessed_mime = mimetypes.guess_type(lbl_doc.file.name)[0] or 'application/octet-stream'
            return FileResponse(open(lbl_doc.file.path, 'rb'), content_type=guessed_mime, filename=Path(lbl_doc.file.name).name)
        raise Http404(f"Document '{clean_field}' not found for application {clean_app_id}.")

    content, filename, mime_type = dms_client.download_document(
        doc_record.dms_reference,
        doc_record.storage_type,
        app.application_id
    )

    if not content:
        raise Http404(f"Could not retrieve document bytes for '{clean_field}'.")

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
