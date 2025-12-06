from django.db import transaction
from django.forms import ValidationError
from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from django.core.exceptions import ValidationError, PermissionDenied
from rest_framework.response import Response
from rest_framework import status
from auth.roles.decorators import has_app_permission
from auth.roles.permissions import HasAppPermission
from auth.workflow.permissions import HasStagePermission
from auth.workflow.models import Workflow, StagePermission, WorkflowTransition, WorkflowStage
from auth.workflow.services import WorkflowService
from .models import SalesmanBarmanModel
from .serializers import SalesmanBarmanSerializer

def _create_application(request, workflow_name: str, serializer_cls):
    """
    1. Load workflow + **initial** stage (the one with is_initial=True)
    2. Save the application (serializer must accept workflow & current_stage)
    3. Determine the role that must receive the first task
    4. Log the **generic** WorkflowTransaction
    5. Return the freshly-created object (fully populated)
    
    """
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



@permission_classes([HasAppPermission('salesman_barman', 'view'), HasStagePermission])
@api_view(['GET'])
def list_salesman_barman(request):
    role = request.user.role.name if request.user.role else None

    valid_admin_roles = ["single_window", "site_admin"]
    if role in valid_admin_roles:
        applications = SalesmanBarmanModel.objects.filter(IsActive=True)
    elif role == "licensee":
        applications = SalesmanBarmanModel.objects.filter(
            IsActive=True,
            current_stage__name__in=["level_1", "awaiting_payment", "level_1_objection", "level_2_objection", "level_3_objection", "level_4_objection", "level_5_objection", "approved"]
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


@permission_classes([HasAppPermission('salesman_barman', 'update'), HasStagePermission])
@api_view(['POST'])
def advance_application(request, application_id, stage_id):
    application = get_object_or_404(SalesmanBarmanModel, application_id=application_id)
    try:
        target_stage = get_object_or_404(WorkflowStage, id=stage_id)
    except WorkflowStage.DoesNotExist:
        return Response({"detail": f"Stage ID {stage_id} not found in workflow {application.workflow.name}."}, status=status.HTTP_404_NOT_FOUND)
    
    context = request.data.get("context", {})
    # remarks = request.data.get("remarks", "")

    try:
        with transaction.atomic():
            WorkflowService.advance_stage(
                application=application,
                user=request.user,
                target_stage=target_stage,
                # remarks=remarks,
                context=context,
            )

            #Return the updated application details
            updated_application = SalesmanBarmanModel.objects.get(id=application.id)
            serializer = SalesmanBarmanSerializer(updated_application)
            return Response(serializer.data, status=status.HTTP_200_OK)

    except ValidationError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
    except PermissionDenied as e:
            return Response({"detail": str(e)}, status=status.HTTP_403_FORBIDDEN)
    except Exception as e:
            return Response({"detail": f"Error advancing stage: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@permission_classes([HasAppPermission('salesman_barman', 'view'), HasStagePermission])
@api_view(['GET'])
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