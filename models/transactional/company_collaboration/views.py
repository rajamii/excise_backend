import json
import re

from django.db import transaction, connection
from django.shortcuts import get_object_or_404
from rest_framework import permissions, status
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from auth.roles.permissions import HasAppPermission
from auth.workflow.models import Workflow, WorkflowStage
from auth.workflow.permissions import HasStagePermission
from auth.workflow.services import WorkflowService

from .models import CompanyCollaboration
from .serializers import CompanyCollaborationSerializer


JSON_FIELDS = ['selected_brand_ids', 'selected_brands', 'fee_structure', 'overview_summary']


def _normalize_json_payload(data):
    normalized = {}
    for key in data.keys():
        normalized[key] = data.get(key)

    for field in JSON_FIELDS:
        value = normalized.get(field)
        if isinstance(value, str) and value.strip():
            try:
                normalized[field] = json.loads(value)
            except json.JSONDecodeError:
                pass
    return normalized


def _extract_strength(value):
    match = re.search(r'(\d+(?:\.\d+)?)\s*%', str(value or ''))
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def _display_label(value, fallback='N/A'):
    text = str(value or '').strip()
    if not text:
        return fallback
    return text.title()


def _resolve_workflow():
    workflow = Workflow.objects.filter(name='Company Collaboration').first()
    if workflow:
        return workflow
    return get_object_or_404(Workflow, name='Company Registration')


def _create_application(request):
    payload = _normalize_json_payload(request.data)
    serializer = CompanyCollaborationSerializer(data=payload)
    serializer.is_valid(raise_exception=True)

    with transaction.atomic():
        workflow = _resolve_workflow()
        initial_stage = workflow.stages.filter(is_initial=True).first()
        if not initial_stage:
            return Response(
                {'detail': 'Workflow has no initial stage (is_initial=True).'},
                status=status.HTTP_400_BAD_REQUEST
            )

        fin_year = CompanyCollaboration.generate_fin_year()
        prefix = f"CCOL/{fin_year}"
        last_app = CompanyCollaboration.objects.filter(
            application_id__startswith=prefix
        ).select_for_update().order_by('-application_id').first()

        last_number = int(last_app.application_id.split('/')[-1]) if last_app else 0
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


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def list_brand_owners(request):
    query = """
        SELECT COALESCE(mfl.factory_name, '') AS factory_name, COUNT(DISTINCT bw.brand_id) AS brand_count
        FROM brand_warehouse bw
        LEFT JOIN master_factory_list mfl ON bw.factory_id = mfl.id
        WHERE COALESCE(mfl.factory_name, '') <> ''
          AND (bw.is_deleted = false OR bw.is_deleted IS NULL)
        GROUP BY mfl.factory_name
        ORDER BY mfl.factory_name
    """

    with connection.cursor() as cursor:
        cursor.execute(query)
        rows = cursor.fetchall()

    data = []
    for factory_name, brand_count in rows:
        name = str(factory_name or '').strip()
        if not name:
            continue

        owner_code = CompanyCollaboration.make_owner_code(name)
        data.append({
            'id': owner_code,
            'brandOwner': name,
            'brandOwnerCode': owner_code,
            'companyName': name,
            'companyAddress': '',
            'location': name,
            'status': 'Active',
            'brandCount': int(brand_count or 0),
        })

    return Response({'success': True, 'data': data})


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def list_brands(request):
    owner_code = request.query_params.get('brand_owner_code') or request.query_params.get('brandOwnerCode')
    owner_name = request.query_params.get('brand_owner') or request.query_params.get('brandOwner')

    owner_distillery = None
    if owner_name:
        owner_distillery = owner_name
    elif owner_code:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT DISTINCT COALESCE(mfl.factory_name, '') AS factory_name
                FROM brand_warehouse bw
                LEFT JOIN master_factory_list mfl ON bw.factory_id = mfl.id
                WHERE COALESCE(mfl.factory_name, '') <> ''
                  AND (bw.is_deleted = false OR bw.is_deleted IS NULL)
                """
            )
            rows = cursor.fetchall()
        for (factory_name,) in rows:
            name = str(factory_name or '').strip()
            if not name:
                continue
            candidate_code = CompanyCollaboration.make_owner_code(name)
            if candidate_code == owner_code:
                owner_distillery = name
                break

    base_query = """
        SELECT COALESCE(mbl.brand_name, '') AS brand_name,
               COALESCE(mfl.factory_name, '') AS factory_name,
               COALESCE(mlt.liquor_type, '') AS brand_type,
               COALESCE(mlc.size_ml, 0) AS capacity_size
        FROM brand_warehouse bw
        LEFT JOIN master_brand_list mbl ON bw.brand_id = mbl.id
        LEFT JOIN master_factory_list mfl ON bw.factory_id = mfl.id
        LEFT JOIN master_liquor_type mlt ON bw.liquor_type = mlt.id
        LEFT JOIN master_liquor_category mlc ON bw.capacity_size = mlc.id
        WHERE COALESCE(mbl.brand_name, '') <> ''
          AND (bw.is_deleted = false OR bw.is_deleted IS NULL)
    """
    params = []
    if owner_distillery:
        base_query += " AND LOWER(COALESCE(mfl.factory_name, '')) = LOWER(%s)"
        params.append(owner_distillery)
    base_query += " ORDER BY mbl.brand_name, COALESCE(mlc.size_ml, 0)"

    with connection.cursor() as cursor:
        cursor.execute(base_query, params)
        rows = cursor.fetchall()

    brand_map = {}
    for brand_name_value, factory_name, brand_type, capacity_size in rows:
        brand_name = str(brand_name_value or '').strip()
        if not brand_name:
            continue

        owner_name_value = str(factory_name or '').strip()
        type_value = str(brand_type or '').strip()
        key = (brand_name, owner_name_value, type_value)

        if key not in brand_map:
            owner_code_value = CompanyCollaboration.make_owner_code(owner_name_value) if owner_name_value else ''
            label_type = _display_label(type_value, 'General')
            brand_map[key] = {
                'id': CompanyCollaboration.make_brand_code(brand_name, owner_name_value),
                'brandCode': CompanyCollaboration.make_brand_code(brand_name, owner_name_value),
                'brandName': brand_name,
                'category': label_type,
                'kind': label_type,
                'type': label_type,
                'strength': _extract_strength(brand_name),
                'sizes': [],
                'brandOwner': owner_name_value,
                'brandOwnerCode': owner_code_value,
                'manufacturingUnitName': owner_name_value,
                'status': 'Active',
            }

        if capacity_size:
            label = f"{capacity_size} Ml"
            if label not in brand_map[key]['sizes']:
                brand_map[key]['sizes'].append(label)

    data = sorted(brand_map.values(), key=lambda item: item['brandName'].lower())
    return Response({'success': True, 'data': data, 'totalBrands': len(data)})


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
@parser_classes([JSONParser, FormParser, MultiPartParser])
def get_fee_structure(request):
    payload = _normalize_json_payload(request.data)
    selected_brand_ids = payload.get('selected_brand_ids') or payload.get('selectedBrandIds') or []
    selected_brands = payload.get('selected_brands') or payload.get('selectedBrands') or []
    brand_count = len(selected_brand_ids or selected_brands or [])

    fee_data = {
        'applicationFee': 1000,
        'collaborationFee': 5000,
        'securityDeposit': 10000,
        'selectedBrandCount': brand_count,
        'totalAmount': 16000,
    }
    return Response({'success': True, 'data': fee_data})


@api_view(['POST'])
@parser_classes([MultiPartParser, FormParser, JSONParser])
@permission_classes([HasStagePermission])
def create_company_collaboration(request):
    try:
        return _create_application(request)
    except Exception as exc:
        return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
@permission_classes([HasAppPermission('company_registration', 'view'), HasStagePermission])
def list_company_collaborations(request):
    role = request.user.role.name if request.user.role else None

    if role in ['single_window', 'site_admin']:
        applications = CompanyCollaboration.objects.all()
    elif role == 'licensee':
        applications = CompanyCollaboration.objects.filter(
            applicant=request.user,
            current_stage__name__in=[
                'level_1',
                'awaiting_payment',
                'level_1_objection',
                'level_2_objection',
                'level_3_objection',
                'level_4_objection',
                'level_5_objection',
                'approved',
            ]
        )
    else:
        applications = CompanyCollaboration.objects.filter(
            current_stage__stagepermission__role=request.user.role,
            current_stage__stagepermission__can_process=True,
        ).distinct()

    return Response(CompanyCollaborationSerializer(applications, many=True).data)


@api_view(['GET'])
@permission_classes([HasAppPermission('company_registration', 'view'), HasStagePermission])
def company_collaboration_detail(request, application_id):
    application = get_object_or_404(CompanyCollaboration, application_id=application_id)
    return Response(CompanyCollaborationSerializer(application).data)


@api_view(['GET'])
@permission_classes([HasAppPermission('company_registration', 'view'), HasStagePermission])
def dashboard_counts(request):
    role = request.user.role.name if request.user.role else None
    counts = {}

    if role in ['level_1', 'level_2', 'level_3', 'level_4', 'level_5']:
        stage = WorkflowStage.objects.get(name=role, workflow=_resolve_workflow())
        counts = {
            'pending': CompanyCollaboration.objects.filter(current_stage=stage).count(),
            'approved': CompanyCollaboration.objects.filter(
                current_stage__name__in=[f"level_{int(role.split('_')[1]) + 1}", 'awaiting_payment', 'approved']
            ).count(),
            'rejected': CompanyCollaboration.objects.filter(
                current_stage__name=f"rejected_by_{role}"
            ).count() if WorkflowStage.objects.filter(name=f"rejected_by_{role}", workflow=_resolve_workflow()).exists() else 0,
        }
    elif role == 'licensee':
        base_qs = CompanyCollaboration.objects.filter(applicant=request.user)
        counts = {
            'applied': base_qs.filter(
                current_stage__name__in=['level_1', 'level_2', 'level_3', 'level_4', 'level_5']
            ).count(),
            'pending': base_qs.filter(
                current_stage__name__in=[
                    'level_1_objection',
                    'level_2_objection',
                    'level_3_objection',
                    'level_4_objection',
                    'level_5_objection',
                    'awaiting_payment',
                ]
            ).count(),
            'approved': base_qs.filter(current_stage__name='approved', is_approved=True).count(),
            'rejected': base_qs.filter(
                current_stage__name__in=[
                    'rejected_by_level_1',
                    'rejected_by_level_2',
                    'rejected_by_level_3',
                    'rejected_by_level_4',
                    'rejected_by_level_5',
                    'rejected',
                ]
            ).count(),
        }
    elif role in ['site_admin', 'single_window']:
        counts = {
            'applied': CompanyCollaboration.objects.filter(
                current_stage__name__in=[
                    'applicant_applied',
                    'level_1_objection',
                    'level_2_objection',
                    'level_3_objection',
                    'level_4_objection',
                    'level_5_objection',
                    'awaiting_payment',
                ]
            ).count(),
            'pending': CompanyCollaboration.objects.filter(
                current_stage__name__in=['level_1', 'level_2', 'level_3', 'level_4', 'level_5']
            ).count(),
            'approved': CompanyCollaboration.objects.filter(current_stage__name='approved', is_approved=True).count(),
            'rejected': CompanyCollaboration.objects.filter(
                current_stage__name__in=[
                    'rejected_by_level_1',
                    'rejected_by_level_2',
                    'rejected_by_level_3',
                    'rejected_by_level_4',
                    'rejected_by_level_5',
                    'rejected',
                ]
            ).count(),
        }
    else:
        return Response({'detail': 'Invalid role'}, status=status.HTTP_400_BAD_REQUEST)

    return Response(counts)


@api_view(['GET'])
@permission_classes([HasAppPermission('company_registration', 'view'), HasStagePermission])
@parser_classes([JSONParser])
def application_group(request):
    role = request.user.role.name if request.user.role else None

    level_map = {
        'level_1': {
            'pending': ['level_1', 'level_1_objection'],
            'approved': ['level_2'],
            'rejected': ['rejected_by_level_1'],
        },
        'level_2': {
            'pending': ['level_2', 'level_2_objection'],
            'approved': ['awaiting_payment', 'level_3'],
            'rejected': ['rejected_by_level_2'],
        },
        'level_3': {
            'pending': ['level_3', 'level_3_objection'],
            'approved': ['level_4'],
            'rejected': ['rejected_by_level_3'],
        },
        'level_4': {
            'pending': ['level_4', 'level_4_objection'],
            'approved': ['level_5'],
            'rejected': ['rejected_by_level_4'],
        },
        'level_5': {
            'pending': ['level_5', 'level_5_objection'],
            'approved': ['approved'],
            'rejected': ['rejected_by_level_5'],
        },
    }

    if role in level_map:
        result = {}
        for key, stages in level_map[role].items():
            queryset = CompanyCollaboration.objects.filter(current_stage__name__in=stages)
            if key == 'rejected':
                queryset = queryset.filter(is_approved=False)
            result[key] = CompanyCollaborationSerializer(queryset, many=True).data
        return Response(result)

    if role == 'licensee':
        base_qs = CompanyCollaboration.objects.filter(applicant=request.user)
        result = {
            'applied': CompanyCollaborationSerializer(
                base_qs.filter(current_stage__name__in=['level_1', 'level_2', 'level_3', 'level_4', 'level_5']),
                many=True,
            ).data,
            'pending': CompanyCollaborationSerializer(
                base_qs.filter(
                    current_stage__name__in=[
                        'level_1_objection',
                        'level_2_objection',
                        'level_3_objection',
                        'level_4_objection',
                        'level_5_objection',
                        'awaiting_payment',
                    ]
                ),
                many=True,
            ).data,
            'approved': CompanyCollaborationSerializer(
                base_qs.filter(current_stage__name='approved'),
                many=True,
            ).data,
            'rejected': CompanyCollaborationSerializer(
                base_qs.filter(
                    current_stage__name__in=[
                        'rejected_by_level_1',
                        'rejected_by_level_2',
                        'rejected_by_level_3',
                        'rejected_by_level_4',
                        'rejected_by_level_5',
                        'rejected',
                    ]
                ),
                many=True,
            ).data,
        }
        return Response(result)

    return Response({'detail': 'Invalid role'}, status=status.HTTP_400_BAD_REQUEST)

