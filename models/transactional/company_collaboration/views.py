import json

from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from auth.roles.permissions import HasAppPermission
from auth.workflow.models import Workflow, WorkflowStage
from auth.workflow.permissions import HasStagePermission
from auth.workflow.services import WorkflowService

from .models import CompanyCollaboration
from .serializers import CompanyCollaborationSerializer

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

JSON_FIELDS = ['selected_brand_ids', 'selected_brands', 'fee_structure', 'overview_summary']


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalize_role(role_name):
    if not role_name:
        return None
    normalized = str(role_name).strip().lower().replace('-', '_').replace(' ', '_')
    aliases = {
        'license_user':  'licensee',
        'licensee_user': 'licensee',
        'singlewindow':  'single_window',
        'siteadmin':     'site_admin',
    }
    return aliases.get(normalized, normalized)


def _normalize_json_payload(data: dict) -> dict:
    normalized = {key: data.get(key) for key in data.keys()}
    for field in JSON_FIELDS:
        value = normalized.get(field)
        if isinstance(value, str) and value.strip():
            try:
                normalized[field] = json.loads(value)
            except json.JSONDecodeError:
                pass
    return normalized


def _resolve_workflow() -> Workflow:
    workflow = Workflow.objects.filter(name='Company Collaboration').first()
    if not workflow:
        raise Http404(
            "Workflow 'Company Collaboration' not found. "
            "Please create it in the Django admin before accepting applications."
        )
    return workflow


# ---------------------------------------------------------------------------
# Application creation
# ---------------------------------------------------------------------------

def _create_application(request) -> Response:
    payload = _normalize_json_payload(request.data)
    serializer = CompanyCollaborationSerializer(data=payload)
    serializer.is_valid(raise_exception=True)

    with transaction.atomic():
        workflow = _resolve_workflow()
        initial_stage = workflow.stages.filter(is_initial=True).first()
        if not initial_stage:
            return Response(
                {'detail': 'Workflow "Company Collaboration" has no initial stage (is_initial=True).'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        fin_year = CompanyCollaboration.generate_fin_year()
        prefix = f"CCOL/{fin_year}"
        last_app = (
            CompanyCollaboration.objects
            .filter(application_id__startswith=prefix)
            .select_for_update()
            .order_by('-application_id')
            .first()
        )
        last_number = 0
        if last_app:
            try:
                last_number = int(last_app.application_id.split('/')[-1])
            except (ValueError, IndexError):
                last_number = 0
        application_id = f"{prefix}/{str(last_number + 1).zfill(4)}"

        application = serializer.save(
            workflow=workflow,
            current_stage=initial_stage,
            application_id=application_id,
            applicant=request.user,
        )

        WorkflowService.submit_application(
            application=application,
            user=request.user,
            remarks='Company collaboration application submitted',
        )

    fresh = CompanyCollaboration.objects.get(pk=application.pk)
    return Response(CompanyCollaborationSerializer(fresh).data, status=status.HTTP_201_CREATED)


# ---------------------------------------------------------------------------
# POST /apply/
# ---------------------------------------------------------------------------

@api_view(['POST'])
@parser_classes([MultiPartParser, FormParser, JSONParser])
@permission_classes([HasStagePermission])
def create_company_collaboration(request):
    try:
        return _create_application(request)
    except Http404 as exc:
        return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as exc:
        return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)


# ---------------------------------------------------------------------------
# GET /list/
# ---------------------------------------------------------------------------

@api_view(['GET'])
@permission_classes([HasAppPermission('company_collaboration', 'view'), HasStagePermission])
def list_company_collaborations(request):
    role = _normalize_role(request.user.role.name if request.user.role else None)

    if role in ['single_window', 'site_admin']:
        applications = CompanyCollaboration.objects.all()
    elif role == 'licensee':
        applications = CompanyCollaboration.objects.filter(applicant=request.user)
    else:
        applications = CompanyCollaboration.objects.filter(
            current_stage__stagepermission__role=request.user.role,
            current_stage__stagepermission__can_process=True,
        ).distinct()

    return Response(CompanyCollaborationSerializer(applications, many=True).data)


# ---------------------------------------------------------------------------
# GET /detail/<application_id>/
# ---------------------------------------------------------------------------

@api_view(['GET'])
@permission_classes([HasAppPermission('company_collaboration', 'view'), HasStagePermission])
def company_collaboration_detail(request, application_id):
    application = get_object_or_404(CompanyCollaboration, application_id=application_id)
    return Response(CompanyCollaborationSerializer(application).data)


# ---------------------------------------------------------------------------
# GET /dashboard-counts/
# ---------------------------------------------------------------------------

@api_view(['GET'])
@permission_classes([HasAppPermission('company_collaboration', 'view'), HasStagePermission])
def dashboard_counts(request):
    role = _normalize_role(request.user.role.name if request.user.role else None)

    if role in ['level_1', 'level_2', 'level_3', 'level_4', 'level_5']:
        workflow  = _resolve_workflow()
        stage     = WorkflowStage.objects.get(name=role, workflow=workflow)
        level_num = int(role.split('_')[1])
        rejected_stage_name = f"rejected_by_{role}"
        counts = {
            'pending': CompanyCollaboration.objects.filter(current_stage=stage).count(),
            'approved': CompanyCollaboration.objects.filter(
                current_stage__name__in=[f"level_{level_num + 1}", 'awaiting_payment', 'approved']
            ).count(),
            'rejected': (
                CompanyCollaboration.objects.filter(current_stage__name=rejected_stage_name).count()
                if WorkflowStage.objects.filter(name=rejected_stage_name, workflow=workflow).exists()
                else 0
            ),
        }

    elif role == 'licensee':
        base_qs = CompanyCollaboration.objects.filter(applicant=request.user)
        counts = {
            'applied':  base_qs.filter(current_stage__name__in=['level_1', 'level_2', 'level_3', 'level_4', 'level_5']).count(),
            'pending':  base_qs.filter(current_stage__name__in=['level_1_objection', 'level_2_objection', 'level_3_objection', 'level_4_objection', 'level_5_objection', 'awaiting_payment']).count(),
            'approved': base_qs.filter(current_stage__name='approved', is_approved=True).count(),
            'rejected': base_qs.filter(current_stage__name__in=['rejected_by_level_1', 'rejected_by_level_2', 'rejected_by_level_3', 'rejected_by_level_4', 'rejected_by_level_5', 'rejected']).count(),
        }

    elif role in ['site_admin', 'single_window']:
        counts = {
            'applied':  CompanyCollaboration.objects.filter(current_stage__name__in=['applicant_applied', 'level_1_objection', 'level_2_objection', 'level_3_objection', 'level_4_objection', 'level_5_objection', 'awaiting_payment']).count(),
            'pending':  CompanyCollaboration.objects.filter(current_stage__name__in=['level_1', 'level_2', 'level_3', 'level_4', 'level_5']).count(),
            'approved': CompanyCollaboration.objects.filter(current_stage__name='approved', is_approved=True).count(),
            'rejected': CompanyCollaboration.objects.filter(current_stage__name__in=['rejected_by_level_1', 'rejected_by_level_2', 'rejected_by_level_3', 'rejected_by_level_4', 'rejected_by_level_5', 'rejected']).count(),
        }

    else:
        return Response({'detail': 'Invalid role.'}, status=status.HTTP_400_BAD_REQUEST)

    return Response(counts)


# ---------------------------------------------------------------------------
# GET /list-by-status/
# ---------------------------------------------------------------------------

@api_view(['GET'])
@permission_classes([HasAppPermission('company_collaboration', 'view'), HasStagePermission])
@parser_classes([JSONParser])
def application_group(request):
    role = _normalize_role(request.user.role.name if request.user.role else None)

    level_map = {
        'level_1': {'pending': ['level_1', 'level_1_objection'],   'approved': ['level_2'],                     'rejected': ['rejected_by_level_1']},
        'level_2': {'pending': ['level_2', 'level_2_objection'],   'approved': ['awaiting_payment', 'level_3'], 'rejected': ['rejected_by_level_2']},
        'level_3': {'pending': ['level_3', 'level_3_objection'],   'approved': ['level_4'],                     'rejected': ['rejected_by_level_3']},
        'level_4': {'pending': ['level_4', 'level_4_objection'],   'approved': ['level_5'],                     'rejected': ['rejected_by_level_4']},
        'level_5': {'pending': ['level_5', 'level_5_objection'],   'approved': ['approved'],                    'rejected': ['rejected_by_level_5']},
    }

    if role in level_map:
        result = {}
        for key, stages in level_map[role].items():
            qs = CompanyCollaboration.objects.filter(current_stage__name__in=stages)
            if key == 'rejected':
                qs = qs.filter(is_approved=False)
            result[key] = CompanyCollaborationSerializer(qs, many=True).data
        return Response(result)

    if role == 'licensee':
        base_qs = CompanyCollaboration.objects.filter(applicant=request.user)
        return Response({
            'applied':   CompanyCollaborationSerializer(base_qs.filter(current_stage__name__in=['level_1', 'level_2', 'level_3', 'level_4', 'level_5']), many=True).data,
            'pending':   CompanyCollaborationSerializer(base_qs.filter(current_stage__name__in=['level_1_objection', 'level_2_objection', 'level_3_objection', 'level_4_objection', 'level_5_objection', 'awaiting_payment']), many=True).data,
            'approved':  CompanyCollaborationSerializer(base_qs.filter(current_stage__name='approved'), many=True).data,
            'rejected':  CompanyCollaborationSerializer(base_qs.filter(current_stage__name__in=['rejected_by_level_1', 'rejected_by_level_2', 'rejected_by_level_3', 'rejected_by_level_4', 'rejected_by_level_5', 'rejected']), many=True).data,
        })

    return Response({'detail': 'Invalid role.'}, status=status.HTTP_400_BAD_REQUEST)
