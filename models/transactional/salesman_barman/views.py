from django.db import transaction
from django.forms import ValidationError
from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from django.core.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework import status
from auth.roles.permissions import HasAppPermission
from auth.workflow.permissions import HasStagePermission
from auth.workflow.models import Workflow, StagePermission, WorkflowStage
from auth.workflow.services import WorkflowService
from .models import SalesmanBarmanModel
from .serializers import SalesmanBarmanSerializer

def _create_application(request, workflow_name: str, serializer_cls):
    
    serializer = serializer_cls(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    with transaction.atomic():
        
        # 1. Workflow & initial stage
        workflow = get_object_or_404(Workflow, name=workflow_name)
        try:
            initial_stage = workflow.stages.get(is_initial=True)
        except WorkflowStage.DoesNotExist:
            return Response(
                {"detail": "Workflow has no initial stage (is_initial=True)."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        district_code = serializer.validated_data['excise_district'].district_code
        prefix = f"SBM/{district_code}/{SalesmanBarmanModel.generate_fin_year()}"
        last_app = SalesmanBarmanModel.objects.filter(
            application_id__startswith=prefix
        ).select_for_update().order_by('-application_id').first()

        last_number = int(last_app.application_id.split('/')[-1]) if last_app else 0
        new_number = str(last_number + 1).zfill(4)
        new_application_id = f"{prefix}/{new_number}"

        
        application = serializer.save(
            workflow=workflow,
            current_stage=initial_stage,
            application_id=new_application_id,
            applicant=request.user
        )

        
        # 3. Who receives the first task?
        sp = StagePermission.objects.filter(stage=initial_stage, can_process=True).first()

        if not sp or not sp.role:
            return Response(
                {"detail": "No role assigned to process the initial stage."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        forwarded_to_role = sp.role
        if not forwarded_to_role:
            raise ValidationError("No role configured for the initial stage.")

        # 4. Generic transaction log (uses WorkflowTransaction, NOT a local model)
        WorkflowService.submit_application(
            application=application,
            user=request.user,
            remarks="Application submitted",
        )

        
        # 5. Return the *fresh* object (includes generic relations)
        fresh = SalesmanBarmanModel.objects.get(pk=application.pk)
        fresh_serializer = serializer_cls(fresh)
        return Response(fresh_serializer.data, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@parser_classes([MultiPartParser, FormParser, JSONParser])
@permission_classes([HasStagePermission])
def create_salesman_barman(request):
    return _create_application(request, "Salesman Barman", SalesmanBarmanSerializer)



@permission_classes([HasAppPermission('license_application', 'view'), HasStagePermission])
@api_view(['GET'])
def list_salesman_barman(request):
    role = request.user.role.name if request.user.role else None

    if role in ["single_window","site_admin"]:
        applications = SalesmanBarmanModel.objects.all()
    elif role == "licensee":
        applications = SalesmanBarmanModel.objects.filter(
            applicant=request.user,
            current_stage__name__in=[ "level_1", "awaiting_payment", "level_1_objection", "level_2_objection", "level_3_objection", "level_4_objection", "level_5_objection", "approved"]
        )
    else:
        applications = SalesmanBarmanModel.objects.filter(
            current_stage__stagepermission__role=request.user.role,
            current_stage__stagepermission__can_process=True
        ).distinct()

    serializer = SalesmanBarmanSerializer(applications, many=True)
    return Response(serializer.data)


@permission_classes([HasAppPermission('salesman_barman', 'view'), HasStagePermission])
@api_view(['GET'])
def salesman_barman_detail(request, application_id):
    app = get_object_or_404(SalesmanBarmanModel, application_id=application_id)
    serializer = SalesmanBarmanSerializer(app)
    return Response(serializer.data)


# Dashboard Counts
@permission_classes([HasAppPermission('new_license_application', 'view'), HasStagePermission])
@api_view(['GET'])
def dashboard_counts(request):
    role = request.user.role.name if request.user.role else None
    counts = {}

    if role in ['level_1', 'level_2', 'level_3', 'level_4', 'level_5']:
        stage = WorkflowStage.objects.get(name=role, workflow__name="License Approval")
        counts = {
            "pending": SalesmanBarmanModel.objects.filter(current_stage=stage).count(),
            "approved": SalesmanBarmanModel.objects.filter(
                current_stage__name__in=[
                    f"level_{int(role.split('_')[1]) + 1}", "awaiting_payment", "approved"
                ]
            ).count(),
            "rejected": SalesmanBarmanModel.objects.filter(
                current_stage__name=f"rejected_by_{role}"
            ).count() if WorkflowStage.objects.filter(name=f"rejected_by_{role}").exists() else 0,
        }

    elif role == 'licensee':
        base_qs = SalesmanBarmanModel.objects.filter(applicant=request.user)
        counts = {
            "applied": base_qs.filter(
                current_stage__name__in=['level_1', 'level_2', 'level_3', 'level_4', 'level_5']).count(),
            "pending": base_qs.filter(
                current_stage__name__in=[
                    'level_1_objection',
                    'level_2_objection',
                    'level_3_objection',
                    'level_4_objection',
                    'level_5_objection',
                    'awaiting_payment'
                ]
            ).count(),
            "approved": base_qs.filter(
                current_stage__name='approved', is_approved=True
            ).count(),
            "rejected": base_qs.filter(
                current_stage__name__in=[
                    'rejected_by_level_1',
                    'rejected_by_level_2',
                    'rejected_by_level_3',
                    'rejected_by_level_4',
                    'rejected_by_level_5',
                    'rejected'
                ]
            ).count()
        }

    elif role in ['site_admin', 'single_window']:
        counts = {
            "applied": SalesmanBarmanModel.objects.filter(current_stage__name__in=[
                'applicant_applied', 'level_1_objection',
                'level_2_objection', 'level_3_objection',
                'level_4_objection', 'level_5_objection',
                'awaiting_payment'
                ]).count(),
            "pending": SalesmanBarmanModel.objects.filter(current_stage__name__in=[
                'level_1','level_2','level_3','level_4','level_5',
                ]).count(),
            "approved": SalesmanBarmanModel.objects.filter(
                current_stage__name='approved', is_approved=True
            ).count(),
            "rejected": SalesmanBarmanModel.objects.filter(
                current_stage__name__in=[
                    'rejected_by_level_1',
                    'rejected_by_level_2',
                    'rejected_by_level_3',
                    'rejected_by_level_4',
                    'rejected_by_level_5',
                    'rejected',
                ]
            ).count()
        }

    else:
        return Response({"detail": "Invalid role"}, status=status.HTTP_400_BAD_REQUEST)

    return Response(counts)

@permission_classes([HasAppPermission('license_application', 'view'), HasStagePermission])
@api_view(['GET'])
@parser_classes([JSONParser])
def application_group(request):
    role = request.user.role.name if request.user.role else None

    level_map = {
        'level_1': {
            "pending": ['level_1', 'level_1_objection'],
            "approved": ['level_2'],
            "rejected": ['rejected_by_level_1'],
        },
        'level_2': {
            "pending": ['level_2', 'level_2_objection'],
            "approved": ['awaiting_payment', 'level_3'],
            "rejected": ['rejected_by_level_2'],
        },
        'level_3': {
            "pending": ['level_3', 'level_3_objection'],
            "approved": ['level_4'],
            "rejected": ['rejected_by_level_3'],
        },
        'level_4': {
            "pending": ['level_4', 'level_4_objection'],
            "approved": ['level_5'],
            "rejected": ['rejected_by_level_4'],
        },
        'level_5': {
            "pending": ['level_5', 'level_5_objection'],
            "approved": ['approved'],
            "rejected": ['rejected_by_level_5'],
        }
    }

    if role in level_map:
        result = {}
        config = level_map[role]
        for key, stages in config.items():
            queryset = SalesmanBarmanModel.objects.filter(current_stage__name__in=stages)
            if key == 'rejected':
                queryset = queryset.filter(is_approved=False)
            result[key] = SalesmanBarmanSerializer(queryset, many=True).data
        return Response(result)

    elif role == 'licensee':
        base_qs = SalesmanBarmanModel.objects.filter(applicant=request.user)
        result = {
            "applied": SalesmanBarmanSerializer(
                base_qs.filter(current_stage__name__in=[
                    'level_1', 'level_2', 'level_3', 'level_4', 'level_5'
                    ]),
                many=True
            ).data,
            "pending": SalesmanBarmanSerializer(
                base_qs.filter(current_stage__name__in=[
                    'level_1_objection',
                    'level_2_objection',
                    'level_3_objection',
                    'level_4_objection',
                    'level_5_objection',
                    'awaiting_payment'
                ]),
                many=True
            ).data,
            "approved": SalesmanBarmanSerializer(
                base_qs.filter(current_stage__name='approved'),
                many=True
            ).data,
            "rejected": SalesmanBarmanSerializer(
                base_qs.filter(current_stage__name__in=[
                    'rejected_by_level_1', 'rejected_by_level_2',
                    'rejected_by_level_3', 'rejected_by_level_4',
                    'rejected_by_level_5', 'rejected'
                ]),
                many=True
            ).data
        }
        return Response(result)

    return Response({"detail": "Invalid role"}, status=status.HTTP_400_BAD_REQUEST)