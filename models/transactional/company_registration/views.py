from django.shortcuts import get_object_or_404
from django.db import transaction
from rest_framework import status
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from auth.roles.decorators import has_app_permission
from auth.workflow.constants import WORKFLOW_IDS
from auth.workflow.models import Workflow, WorkflowStage, WorkflowTransition
from auth.workflow.permissions import HasStagePermission
from auth.workflow.services import WorkflowService

from .models import CompanyModel
from .serializers import CompanySerializer

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


def _resolve_company_workflow():
    workflow_id = WORKFLOW_IDS.get('COMPANY_REGISTRATION')
    if workflow_id is not None:
        try:
            return Workflow.objects.get(id=workflow_id)
        except Workflow.DoesNotExist:
            pass

    # Fallback: resolve dynamically by workflow name if constant is not defined.
    for workflow_name in ('Company Registration', 'company_registration', 'company registration'):
        workflow = Workflow.objects.filter(name__iexact=workflow_name).first()
        if workflow:
            return workflow
    return None


def _get_stage_sets(workflow_id: int):
    stages = WorkflowStage.objects.filter(workflow_id=workflow_id)
    stage_names = set(stages.values_list('name', flat=True))
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
        'objection': objection_stage_names,
        'rejected': rejected_stage_names,
        'approved': approved_stage_names,
        'payment': payment_stage_names,
        'initial': initial_stage_names,
    }


def _get_in_progress_stage_names(stage_sets: dict):
    return set(stage_sets['all']) - set(stage_sets['approved']) - set(stage_sets['rejected'])


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

    return {
        'pending': set(role_stage_names),
        'approved': set(approved_targets) | set(stage_sets['approved']) | set(stage_sets['payment']),
        'rejected': set(rejected_targets) | set(stage_sets['rejected']),
        'objection': set(objection_targets) | set(stage_sets['objection']),
    }

#################################################
#           Company Registration                #
#################################################

@has_app_permission('company_registration', 'view')
@api_view(['GET'])
def company_list(request):
    """List active company registrations with filters"""
    role = _normalize_role(request.user.role.name if getattr(request.user, 'role', None) else None)

    if role in ['single_window', 'site_admin']:
        queryset = CompanyModel.objects.filter(IsActive=True)
    elif role == 'licensee':
        queryset = CompanyModel.objects.filter(IsActive=True, applicant=request.user)
    else:
        queryset = CompanyModel.objects.filter(
            IsActive=True,
            current_stage__stagepermission__role=request.user.role,
            current_stage__stagepermission__can_process=True,
        ).distinct()
    
    # Optional filters
    application_year = request.query_params.get('application_year')
    company_name = request.query_params.get('company_name')
    pan = request.query_params.get('pan')
    brand_type = request.query_params.get('brand_type')
    
    if application_year:
        queryset = queryset.filter(applicationYear=application_year)
    if company_name:
        queryset = queryset.filter(companyName__icontains=company_name)
    if pan:
        queryset = queryset.filter(pan=pan)
    if brand_type:
        queryset = queryset.filter(brandType=brand_type)
    
    serializer = CompanySerializer(queryset, many=True)
    return Response({
        'count': queryset.count(),
        'results': serializer.data
    })

@has_app_permission('company_registration', 'create')
@api_view(['POST'])
@parser_classes([MultiPartParser, FormParser, JSONParser])
@permission_classes([HasStagePermission])
def company_create(request):
    """Create and submit new company registration into configured workflow."""
    serializer = CompanySerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    workflow = _resolve_company_workflow()
    if not workflow:
        return Response(
            {"detail": "Company registration workflow not configured."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    initial_stage = workflow.stages.filter(is_initial=True).first()
    if not initial_stage:
        return Response(
            {"detail": "Workflow has no initial stage (is_initial=True)."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    with transaction.atomic():
        fin_year = CompanyModel.generate_fin_year()
        prefix = f"COMP/{fin_year}"
        last_obj = CompanyModel.objects.filter(
            applicationId__startswith=prefix
        ).select_for_update().order_by('-applicationId').first()

        last_number = int(last_obj.applicationId.split('/')[-1]) if last_obj and last_obj.applicationId else 0
        next_number = str(last_number + 1).zfill(4)
        application_id = f"{prefix}/{next_number}"

        application = serializer.save(
            workflow=workflow,
            current_stage=initial_stage,
            applicant=request.user,
            applicationId=application_id,
        )

        WorkflowService.submit_application(
            application=application,
            user=request.user,
            remarks="Application submitted",
        )

    fresh = CompanyModel.objects.get(pk=application.pk)
    return Response(CompanySerializer(fresh).data, status=status.HTTP_201_CREATED)

@has_app_permission('company_registration', 'view')
@api_view(['GET'])
def company_detail(request, pk):
    """Retrieve active company registration by PK"""
    company = get_object_or_404(CompanyModel, pk=pk, IsActive=True)
    serializer = CompanySerializer(company)
    return Response(serializer.data)

@has_app_permission('company_registration', 'view')
@api_view(['GET'])
def company_detail_by_appid(request, application_id):
    """Retrieve active company registration by application ID"""
    company = get_object_or_404(
        CompanyModel, 
        applicationId=application_id, 
        IsActive=True
    )
    serializer = CompanySerializer(company)
    return Response(serializer.data)

@has_app_permission('company_registration', 'update')
@api_view(['PUT', 'PATCH'])
@parser_classes([MultiPartParser, FormParser])
def company_update(request, pk):
    """Update company registration by PK"""
    company = get_object_or_404(CompanyModel, pk=pk)
    serializer = CompanySerializer(
        instance=company,
        data=request.data,
        partial=request.method == 'PATCH'
    )
    
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@has_app_permission('company_registration', 'update')
@api_view(['PUT', 'PATCH'])
@parser_classes([MultiPartParser, FormParser])
def company_update_by_appid(request, application_id):
    """Update company registration by application ID"""
    company = get_object_or_404(
        CompanyModel, 
        applicationId=application_id
    )
    serializer = CompanySerializer(
        instance=company,
        data=request.data,
        partial=request.method == 'PATCH'
    )
    
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@has_app_permission('company_registration', 'delete')
@api_view(['DELETE'])
def company_delete(request, pk):
    """Soft delete company registration by PK"""
    company = get_object_or_404(CompanyModel, pk=pk)
    company.IsActive = False
    company.save()
    return Response(
        {'message': f'Company {company.companyName} deactivated'},
        status=status.HTTP_200_OK
    )

@has_app_permission('company_registration', 'delete')
@api_view(['DELETE'])
def company_delete_by_appid(request, application_id):
    """Soft delete company registration by application ID"""
    company = get_object_or_404(
        CompanyModel, 
        applicationId=application_id
    )
    company.IsActive = False
    company.save()
    return Response(
        {'message': f'Company {company.companyName} deactivated'},
        status=status.HTTP_200_OK
    )


@has_app_permission('company_registration', 'view')
@api_view(['GET'])
@permission_classes([HasStagePermission])
def dashboard_counts(request):
    workflow = _resolve_company_workflow()
    if not workflow:
        return Response({"detail": "Company registration workflow not configured."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    workflow_id = workflow.id
    stage_sets = _get_stage_sets(workflow_id)
    role = _normalize_role(request.user.role.name if getattr(request.user, 'role', None) else None)
    all_qs = CompanyModel.objects.filter(IsActive=True)

    if role == 'licensee':
        base_qs = all_qs.filter(applicant=request.user)
        applied_stages = set(stage_sets['initial'])
        pending_stages = _get_in_progress_stage_names(stage_sets) - applied_stages
        return Response({
            "applied": base_qs.filter(current_stage__name__in=applied_stages).count(),
            "pending": base_qs.filter(current_stage__name__in=pending_stages).count(),
            "approved": base_qs.filter(current_stage__name__in=stage_sets['approved']).count(),
            "rejected": base_qs.filter(current_stage__name__in=stage_sets['rejected']).count(),
            "objection": base_qs.filter(current_stage__name__in=stage_sets['objection']).count(),
        })

    if role in ['site_admin', 'single_window']:
        return Response({
            "pending": all_qs.filter(current_stage__name__in=_get_in_progress_stage_names(stage_sets)).count(),
            "approved": all_qs.filter(current_stage__name__in=stage_sets['approved']).count(),
            "rejected": all_qs.filter(current_stage__name__in=stage_sets['rejected']).count(),
            "objection": all_qs.filter(current_stage__name__in=stage_sets['objection']).count(),
        })

    buckets = _build_role_transition_buckets(request.user, workflow_id, stage_sets)
    if not buckets:
        return Response({"detail": "Invalid role"}, status=status.HTTP_400_BAD_REQUEST)

    return Response({
        "pending": all_qs.filter(current_stage__name__in=buckets['pending']).count(),
        "approved": all_qs.filter(current_stage__name__in=buckets['approved']).count(),
        "rejected": all_qs.filter(current_stage__name__in=buckets['rejected']).count(),
        "objection": all_qs.filter(current_stage__name__in=buckets['objection']).count(),
    })


@has_app_permission('company_registration', 'view')
@api_view(['GET'])
@permission_classes([HasStagePermission])
def application_group(request):
    workflow = _resolve_company_workflow()
    if not workflow:
        return Response({"detail": "Company registration workflow not configured."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    workflow_id = workflow.id
    stage_sets = _get_stage_sets(workflow_id)
    role = _normalize_role(request.user.role.name if getattr(request.user, 'role', None) else None)
    all_qs = CompanyModel.objects.filter(IsActive=True)

    if role == 'licensee':
        base_qs = all_qs.filter(applicant=request.user)
        applied_stages = set(stage_sets['initial'])
        pending_stages = _get_in_progress_stage_names(stage_sets) - applied_stages
        return Response({
            "applied": CompanySerializer(base_qs.filter(current_stage__name__in=applied_stages), many=True).data,
            "pending": CompanySerializer(base_qs.filter(current_stage__name__in=pending_stages), many=True).data,
            "approved": CompanySerializer(base_qs.filter(current_stage__name__in=stage_sets['approved']), many=True).data,
            "rejected": CompanySerializer(base_qs.filter(current_stage__name__in=stage_sets['rejected']), many=True).data,
            "objection": CompanySerializer(base_qs.filter(current_stage__name__in=stage_sets['objection']), many=True).data,
        })

    if role in ['site_admin', 'single_window']:
        return Response({
            "pending": CompanySerializer(all_qs.filter(current_stage__name__in=_get_in_progress_stage_names(stage_sets)), many=True).data,
            "approved": CompanySerializer(all_qs.filter(current_stage__name__in=stage_sets['approved']), many=True).data,
            "rejected": CompanySerializer(all_qs.filter(current_stage__name__in=stage_sets['rejected']), many=True).data,
            "objection": CompanySerializer(all_qs.filter(current_stage__name__in=stage_sets['objection']), many=True).data,
        })

    buckets = _build_role_transition_buckets(request.user, workflow_id, stage_sets)
    if not buckets:
        return Response({"detail": "Invalid role"}, status=status.HTTP_400_BAD_REQUEST)

    return Response({
        "pending": CompanySerializer(all_qs.filter(current_stage__name__in=buckets['pending']), many=True).data,
        "approved": CompanySerializer(all_qs.filter(current_stage__name__in=buckets['approved']), many=True).data,
        "rejected": CompanySerializer(all_qs.filter(current_stage__name__in=buckets['rejected']), many=True).data,
        "objection": CompanySerializer(all_qs.filter(current_stage__name__in=buckets['objection']), many=True).data,
    })
