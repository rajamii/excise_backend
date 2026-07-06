from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.parsers import JSONParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from auth.workflow.models import Workflow
from auth.workflow.services import WorkflowService
from models.masters.license.models import License
from models.transactional.helpers import _get_role_stage_names, _get_stage_sets, _normalize_role

from .models import SpecialPermitApplication
from .serializers import SpecialPermitApplicationSerializer


def _get_special_permit_workflow() -> Workflow | None:
    return (
        Workflow.objects.filter(name='Special Permit').order_by('id').first()
        or Workflow.objects.filter(name='Special Permission for Dry Day').order_by('id').first()
        or Workflow.objects.filter(name='License Approval').order_by('id').first()
    )


def _serialize_license(license_obj: License) -> dict:
    source_application = getattr(license_obj, 'source_application', None)
    establishment_name = None
    if source_application:
        for field in ('establishment_name', 'business_premises_name', 'company_name', 'applicant_name'):
            value = getattr(source_application, field, None)
            if value:
                establishment_name = str(value)
                break

    return {
        'license_id': license_obj.license_id,
        'district': getattr(license_obj.excise_district, 'district', None),
        'district_code': getattr(license_obj.excise_district, 'district_code', None),
        'license_category': getattr(license_obj.license_category, 'license_category', None),
        'license_sub_category': getattr(license_obj.license_sub_category, 'description', None),
        'establishment_name': establishment_name,
        'valid_up_to': license_obj.valid_up_to.isoformat() if license_obj.valid_up_to else None,
        'is_active': license_obj.is_active,
    }


def _visible_queryset(request):
    role = _normalize_role(request.user.role.name if getattr(request.user, 'role', None) else None)
    qs = SpecialPermitApplication.objects.select_related(
        'license',
        'applicant',
        'excise_district',
        'license_category',
        'license_sub_category',
        'workflow',
        'current_stage',
    )

    if role == 'licensee':
        return qs.filter(applicant=request.user)

    wf = _get_special_permit_workflow()
    if not wf or role in ('site_admin', 'single_window'):
        return qs

    role_stage_names = _get_role_stage_names(request.user, wf.id)
    if not role_stage_names:
        return qs.none()
    return qs.filter(current_stage__name__in=role_stage_names)


def _status_sets(workflow):
    if not workflow:
        return {
            'applied': set(),
            'pending': set(),
            'objection': set(),
            'approved': set(),
            'rejected': set(),
            'payment': set(),
        }
    stage_sets = _get_stage_sets(workflow.id)
    applied_stages = set(stage_sets['initial'])
    objection_stages = set(stage_sets['objection'])
    approved_stages = set(stage_sets['approved'])
    rejected_stages = set(stage_sets['rejected'])
    payment_stages = set(stage_sets['payment'])
    pending_stages = set(stage_sets['all']) - applied_stages - approved_stages - rejected_stages - objection_stages - payment_stages
    return {
        'applied': applied_stages,
        'pending': pending_stages,
        'objection': objection_stages,
        'approved': approved_stages,
        'rejected': rejected_stages,
        'payment': payment_stages,
    }


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def eligible_licenses(request):
    now_dt = timezone.now()
    licenses = License.objects.filter(
        applicant=request.user,
        is_active=True,
        valid_up_to__gte=now_dt,
    ).select_related('excise_district', 'license_category', 'license_sub_category')
    return Response([_serialize_license(license_obj) for license_obj in licenses], status=status.HTTP_200_OK)


@api_view(['POST'])
@parser_classes([JSONParser])
@permission_classes([IsAuthenticated])
def create_special_permit_application(request):
    license_id = request.data.get('license') or request.data.get('license_id') or request.data.get('licenseId')
    if not license_id:
        return Response({'license': 'This field is required.'}, status=status.HTTP_400_BAD_REQUEST)

    license_obj = get_object_or_404(
        License.objects.select_related('excise_district', 'license_category', 'license_sub_category'),
        license_id=str(license_id),
    )
    if license_obj.applicant_id != request.user.id:
        return Response({'detail': 'You can only apply special permit for your own license.'}, status=status.HTTP_403_FORBIDDEN)
    if not license_obj.is_active or (license_obj.valid_up_to and license_obj.valid_up_to < timezone.now()):
        return Response({'detail': 'Special permit can be applied only against an active license.'}, status=status.HTTP_400_BAD_REQUEST)

    permission_duration = request.data.get('permission_duration') or request.data.get('permissionDuration') or SpecialPermitApplication.PERMISSION_DURATION_PER_ANNUM
    permission_date = request.data.get('permission_date') or request.data.get('permissionDate') or None
    financial_year = request.data.get('financial_year') or request.data.get('financialYear') or SpecialPermitApplication.generate_fin_year()

    serializer = SpecialPermitApplicationSerializer(data={
        'license': license_obj.license_id,
        'financial_year': financial_year,
        'permission_duration': permission_duration,
        'permission_date': permission_date,
        'remarks': request.data.get('remarks', ''),
    })
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    workflow = _get_special_permit_workflow()
    if not workflow:
        return Response({'detail': 'Special Permit workflow is not configured.'}, status=status.HTTP_400_BAD_REQUEST)
    initial_stage = workflow.stages.filter(is_initial=True).order_by('id').first()
    if not initial_stage:
        return Response({'detail': 'Special Permit workflow has no initial stage.'}, status=status.HTTP_400_BAD_REQUEST)

    application = serializer.save(
        application_id=SpecialPermitApplication.generate_application_id(license_obj, financial_year),
        license=license_obj,
        applicant=request.user,
        excise_district=license_obj.excise_district,
        license_category=license_obj.license_category,
        license_sub_category=license_obj.license_sub_category,
        workflow=workflow,
        current_stage=initial_stage,
    )
    WorkflowService.submit_application(
        application=application,
        user=request.user,
        remarks='Special Permit application submitted',
    )
    return Response(SpecialPermitApplicationSerializer(application).data, status=status.HTTP_201_CREATED)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_special_permit_applications(request):
    return Response(SpecialPermitApplicationSerializer(_visible_queryset(request), many=True).data, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def special_permit_detail(request, application_id):
    application = get_object_or_404(_visible_queryset(request), application_id=str(application_id))
    return Response(SpecialPermitApplicationSerializer(application).data, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def dashboard_counts(request):
    workflow = _get_special_permit_workflow()
    status_sets = _status_sets(workflow)
    qs = _visible_queryset(request)

    month = request.query_params.get('month')
    year = request.query_params.get('year')
    if month:
        qs = qs.filter(created_at__month=month)
    if year:
        qs = qs.filter(created_at__year=year)

    return Response({
        'applied': qs.filter(current_stage__name__in=status_sets['applied']).count(),
        'pending': qs.filter(current_stage__name__in=status_sets['pending']).count(),
        'objection': qs.filter(current_stage__name__in=status_sets['objection']).count(),
        'approved': qs.filter(current_stage__name__in=status_sets['approved']).count(),
        'rejected': qs.filter(current_stage__name__in=status_sets['rejected']).count(),
        'awaiting_payment': qs.filter(current_stage__name__in=status_sets['payment']).count(),
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def application_group(request):
    workflow = _get_special_permit_workflow()
    status_sets = _status_sets(workflow)
    qs = _visible_queryset(request)

    return Response({
        'applied': SpecialPermitApplicationSerializer(qs.filter(current_stage__name__in=status_sets['applied']), many=True).data,
        'pending': SpecialPermitApplicationSerializer(qs.filter(current_stage__name__in=status_sets['pending']), many=True).data,
        'objection': SpecialPermitApplicationSerializer(qs.filter(current_stage__name__in=status_sets['objection']), many=True).data,
        'approved': SpecialPermitApplicationSerializer(qs.filter(current_stage__name__in=status_sets['approved']), many=True).data,
        'rejected': SpecialPermitApplicationSerializer(qs.filter(current_stage__name__in=status_sets['rejected']), many=True).data,
        'awaiting_payment': SpecialPermitApplicationSerializer(qs.filter(current_stage__name__in=status_sets['payment']), many=True).data,
    }, status=status.HTTP_200_OK)
