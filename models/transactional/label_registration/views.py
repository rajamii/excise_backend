import json
from datetime import date

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response

from auth.workflow.permissions import HasStagePermission
from .models import LabelRegistration
from .serializers import LabelRegistrationSerializer


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


@api_view(['POST'])
@parser_classes([MultiPartParser, FormParser])
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
    except ValueError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    application_date = _parse_iso_date(request.data.get('application_date'))
    prefix = f"LBL/{application_date.strftime('%Y%m%d')}"

    with transaction.atomic():
        last_app = (
            LabelRegistration.objects.filter(application_id__startswith=prefix)
            .select_for_update()
            .order_by('-application_id')
            .first()
        )
        last_number = int(last_app.application_id.split('/')[-1]) if last_app else 0
        new_number = str(last_number + 1).zfill(4)
        application_id = f"{prefix}/{new_number}"

        application = LabelRegistration.objects.create(
            application_id=application_id,
            applicant=request.user,
            status='Submitted',
            application_date=application_date,
            licensee_details=licensee_details,
            product_details=product_details,
            packaging_details=packaging_details,
        )

    return Response(LabelRegistrationSerializer(application).data, status=status.HTTP_201_CREATED)


@api_view(['GET'])
@permission_classes([HasStagePermission])
def list_label_registrations(request):
    role = request.user.role.name if getattr(request.user, 'role', None) else None

    if role in ['single_window', 'site_admin']:
        queryset = LabelRegistration.objects.all()
    elif role == 'licensee':
        queryset = LabelRegistration.objects.filter(applicant=request.user)
    else:
        queryset = LabelRegistration.objects.all()

    return Response(LabelRegistrationSerializer(queryset, many=True).data)


@api_view(['GET'])
@permission_classes([HasStagePermission])
def label_registration_detail(request, application_id):
    role = request.user.role.name if getattr(request.user, 'role', None) else None

    queryset = LabelRegistration.objects.all()
    if role == 'licensee':
        queryset = queryset.filter(applicant=request.user)

    application = get_object_or_404(queryset, application_id=application_id)
    return Response(LabelRegistrationSerializer(application).data)
