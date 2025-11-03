from django.db import transaction
from django.forms import ValidationError
from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.parsers import MultiPartParser, FormParser
from django.core.exceptions import ValidationError, PermissionDenied
from rest_framework.response import Response
from rest_framework import status
from auth.roles.decorators import has_app_permission
from auth.roles.permissions import HasAppPermission
from auth.workflow.permissions import HasStagePermission
from auth.workflow.models import Workflow, WorkflowStage, StagePermission, WorkflowTransition
from auth.workflow.services import WorkflowService
from .models import SalesmanBarmanModel, SalesmanBarmanTransaction
from .serializers import SalesmanBarmanSerializer

@api_view(['POST'])
@parser_classes([MultiPartParser, FormParser])
@has_app_permission('salesman_barman', 'create')
def create_salesman_barman(request):
    serializer = SalesmanBarmanSerializer(data=request.data)
    if serializer.is_valid():
        with transaction.atomic():
            workflow = get_object_or_404(Workflow, name="Salesman Barman")
            initial_stage = workflow.stages.filter(name="level_1").first()
            if not initial_stage:
                return Response({"detail": "No initial stage defined"}, status=status.HTTP_400_BAD_REQUEST)

            application = serializer.save(
                workflow=workflow,
                current_stage=initial_stage
            )

            #Assign role for the first stage of the workflow
            forwarded_to_role=None
            sp = StagePermission.objects.filter(stage=initial_stage, can_process=True)
            if sp.exists():
                forwarded_to_role=sp.first().role
            if not forwarded_to_role:
                raise ValidationError("No role found for next stage")

            SalesmanBarmanTransaction.objects.create(
                application=application,
                performed_by=request.user,
                forwarded_by=request.user,
                forwarded_to=forwarded_to_role,
                stage=initial_stage,
                remarks="Application submitted"
            )

            #Return the updated application details
            updated_application= SalesmanBarmanModel.objects.get(application_id=application.application_id)
            updated_serializer=SalesmanBarmanSerializer(updated_application)
            return Response(updated_serializer.data, status=status.HTTP_201_CREATED)

    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
@permission_classes([HasAppPermission('salesman_barman', 'view'), HasStagePermission])
def list_salesman_barman(request):
    role = request.user.role.name if request.user.role else None

    valid_admin_roles = ["single_window", "site_admin"]
    if role in valid_admin_roles:
        applications = SalesmanBarmanModel.objects.filter(IsActive=True)
    elif role == "licensee":
        applications = SalesmanBarmanModel.objects.filter(
            IsActive=True,
            current_stage__name__in=["level_1", "awaiting_payment", ...]
        )
    else:
        applications = SalesmanBarmanModel.objects.filter(
            IsActive=True,
            current_stage__stagepermission__role=request.user.role,
            current_stage__stagepermission__can_process=True
        ).distinct()

    serializer = SalesmanBarmanSerializer(applications, many=True)
    return Response(serializer.data)


@api_view(['GET'])
@permission_classes([HasAppPermission('salesman_barman', 'view'), HasStagePermission])
def detail_salesman_barman(request, application_id):
    app = get_object_or_404(SalesmanBarmanModel, application_id=application_id)
    serializer = SalesmanBarmanSerializer(app)
    return Response(serializer.data)


@api_view(['POST'])
@permission_classes([HasAppPermission('salesman_barman', 'update'), HasStagePermission])
def advance_application(request, application_id, stage_id):
    application = get_object_or_404(SalesmanBarmanModel, application_id=application_id)
    try:
        target_stage = get_object_or_404(WorkflowStage, id=stage_id, workflow=application.workflow)
    except WorkflowStage.DoesNotExist:
        return Response({"detail": f"Stage ID {stage_id} not found in workflow {application.workflow.name}."}, status=status.HTTP_404_NOT_FOUND)
    
    context = request.data.get("context", {})
    remarks = request.data.get("remarks", "")

    try:
        with transaction.atomic():
            WorkflowService.advance_stage(
                application=application,
                user=request.user,
                target_stage=target_stage,
                remarks=remarks,
                context_data=context,
            )

            #Return the updated application details
            application = SalesmanBarmanModel.objects.get(id=application.id)
            serializer = SalesmanBarmanSerializer(application)
            return Response(serializer.data, status=status.HTTP_200_OK)

    except ValidationError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
    except PermissionDenied as e:
            return Response({"detail": str(e)}, status=status.HTTP_403_FORBIDDEN            )
    except Exception as e:
            return Response({"detail": f"Error advancing stage: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([HasAppPermission('salesman_barman', 'view'), HasStagePermission])
def get_next_stages(request, application_id):
    application = get_object_or_404(SalesmanBarmanModel, application_id=application_id)
    current_stage = application.current_stage

    # Get all transitions from current stage within the same workflow
    transitions = WorkflowTransition.objects.filter(workflow=application.workflow, from_stage=current_stage)
    allowed_stages = [t.to_stage for t in transitions]
    data = [{
         'id': stage.id,
         'name': stage.name,
         'description': stage.description
    } for stage in allowed_stages]
    
    return Response(data)

# salesman_barman/views.py (add these views)
@api_view(['GET'])
@permission_classes([HasAppPermission('salesman_barman', 'view')])
def dashboard_counts(request):
    qs = SalesmanBarmanModel.objects.filter(IsActive=True)
    data = {
        'applied': qs.filter(current_stage__name='level_1').count(),  # Adjust as needed
        'pending': qs.filter(current_stage__name__in=['level_1', 'level_2', 'level_3', 'level_4', 'level_5']).count(),
        'approved': qs.filter(is_approved=True).count(),
        'rejected': qs.filter(current_stage__name__startswith='rejected').count(),
    }
    return Response(data)

@api_view(['GET'])
@permission_classes([HasAppPermission('salesman_barman', 'view')])
def applications_by_status(request):
    qs = SalesmanBarmanModel.objects.filter(IsActive=True)
    # Filter by role similar to list_sb_applications
    # ...
    data = {
        'applied': SalesmanBarmanSerializer(qs.filter(current_stage__name='level_1'), many=True).data,
        'pending': SalesmanBarmanSerializer(qs.filter(current_stage__name__in=['level_1', 'level_2', 'level_3', 'level_4', 'level_5']), many=True).data,
        'approved': SalesmanBarmanSerializer(qs.filter(is_approved=True), many=True).data,
        'rejected': SalesmanBarmanSerializer(qs.filter(current_stage__name__startswith='rejected'), many=True).data,
    }
    return Response(data)