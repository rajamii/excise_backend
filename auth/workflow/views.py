from datetime import timezone
from rest_framework.response import Response
from django.apps import apps
from django.forms import ValidationError
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework import status
from rest_framework.exceptions import PermissionDenied
from importlib import import_module
from .models import Workflow, WorkflowStage, WorkflowTransition, StagePermission, Objection
from .serializers import WorkflowSerializer, WorkflowStageSerializer, WorkflowTransitionSerializer, WorkflowObjectionSerializer, StagePermissionSerializer
from auth.roles.permissions import HasAppPermission
from .permissions import HasStagePermission
from .services import WorkflowService
from models.transactional.license_application.models import LicenseApplication
from models.transactional.new_license_application.models import NewLicenseApplication

# Workflow views (from previous response)
@permission_classes([HasAppPermission('workflows', 'view')])
@api_view(['GET'])
def workflow_list(request):
    workflows = Workflow.objects.all()
    serializer = WorkflowSerializer(workflows, many=True)
    return Response(serializer.data)

@permission_classes([HasAppPermission('workflows', 'create')])
@api_view(['POST'])
def workflow_create(request):
    serializer = WorkflowSerializer(data=request.data)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@permission_classes([HasAppPermission('workflows', 'update')])
@api_view(['PUT'])
def workflow_update(request, pk):
    try:
        workflow = Workflow.objects.get(pk=pk)
    except Workflow.DoesNotExist:
        return Response({"detail": "Workflow not found"}, status=status.HTTP_404_NOT_FOUND)
    serializer = WorkflowSerializer(workflow, data=request.data, partial=True)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@permission_classes([HasAppPermission('workflows', 'delete')])
@api_view(['DELETE'])
def workflow_delete(request, pk):
    try:
        workflow = Workflow.objects.get(pk=pk)
    except Workflow.DoesNotExist:
        return Response({"detail": "Workflow not found"}, status=status.HTTP_404_NOT_FOUND)
    workflow.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)

# WorkflowStage views
@permission_classes([HasAppPermission('workflows', 'view')])
@api_view(['GET'])
def workflow_stage_list(request):
    stages = WorkflowStage.objects.all()
    serializer = WorkflowStageSerializer(stages, many=True)
    return Response(serializer.data)

@permission_classes([HasAppPermission('workflows', 'create')])
@api_view(['POST'])
def workflow_stage_create(request):
    serializer = WorkflowStageSerializer(data=request.data)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@permission_classes([HasAppPermission('workflows', 'update')])
@api_view(['PUT'])
def workflow_stage_update(request, pk):
    try:
        stage = WorkflowStage.objects.get(pk=pk)
    except WorkflowStage.DoesNotExist:
        return Response({"detail": "Workflow stage not found"}, status=status.HTTP_404_NOT_FOUND)
    serializer = WorkflowStageSerializer(stage, data=request.data, partial=True)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@permission_classes([HasAppPermission('workflows', 'delete')])
@api_view(['DELETE'])
def workflow_stage_delete(request, pk):
    try:
        stage = WorkflowStage.objects.get(pk=pk)
    except WorkflowStage.DoesNotExist:
        return Response({"detail": "Workflow stage not found"}, status=status.HTTP_404_NOT_FOUND)
    stage.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)

# WorkflowTransition views
@permission_classes([HasAppPermission('workflows', 'view')])
@api_view(['GET'])
def workflow_transition_list(request):
    transitions = WorkflowTransition.objects.all()
    serializer = WorkflowTransitionSerializer(transitions, many=True)
    return Response(serializer.data)

@permission_classes([HasAppPermission('workflows', 'create')])
@api_view(['POST'])
def workflow_transition_create(request):
    serializer = WorkflowTransitionSerializer(data=request.data)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@permission_classes([HasAppPermission('workflows', 'update')])
@api_view(['PUT'])
def workflow_transition_update(request, pk):
    try:
        transition = WorkflowTransition.objects.get(pk=pk)
    except WorkflowTransition.DoesNotExist:
        return Response({"detail": "Workflow transition not found"}, status=status.HTTP_404_NOT_FOUND)
    serializer = WorkflowTransitionSerializer(transition, data=request.data, partial=True)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@permission_classes([HasAppPermission('workflows', 'delete')])
@api_view(['DELETE'])
def workflow_transition_delete(request, pk):
    try:
        transition = WorkflowTransition.objects.get(pk=pk)
    except WorkflowTransition.DoesNotExist:
        return Response({"detail": "Workflow transition not found"}, status=status.HTTP_404_NOT_FOUND)
    transition.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)

# StagePermission views
@permission_classes([HasAppPermission('workflows', 'view')])
@api_view(['GET'])
def stage_permission_list(request):
    permissions = StagePermission.objects.all()
    serializer = StagePermissionSerializer(permissions, many=True)
    return Response(serializer.data)

@permission_classes([HasAppPermission('workflows', 'create')])
@api_view(['POST'])
def stage_permission_create(request):
    serializer = StagePermissionSerializer(data=request.data)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@permission_classes([HasAppPermission('workflows', 'update')])
@api_view(['PUT'])
def stage_permission_update(request, pk):
    try:
        permission = StagePermission.objects.get(pk=pk)
    except StagePermission.DoesNotExist:
        return Response({"detail": "Stage permission not found"}, status=status.HTTP_404_NOT_FOUND)
    serializer = StagePermissionSerializer(permission, data=request.data, partial=True)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@permission_classes([HasAppPermission('workflows', 'delete')])
@api_view(['DELETE'])
def stage_permission_delete(request, pk):
    try:
        permission = StagePermission.objects.get(pk=pk)
    except StagePermission.DoesNotExist:
        return Response({"detail": "Stage permission not found"}, status=status.HTTP_404_NOT_FOUND)
    permission.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)

# --------------- Common Views ---------------
# Next Stages
@api_view(['GET'])
@permission_classes([HasStagePermission])
def get_next_stages(request, application_id):
    try:
        application = NewLicenseApplication.objects.get(application_id = application_id)
    except NewLicenseApplication.DoesNotExist:
        try:
            application = LicenseApplication.objects.get(application_id = application_id)
        except LicenseApplication.DoesNotExist:
            return Response({"detail": "Application not found"}, status=status.HTTP_404_NOT_FOUND)
        
    current_stage = application.current_stage
    transitions = WorkflowTransition.objects.filter(workflow=application.workflow, from_stage=current_stage)
    allowed_stages = [t.to_stage for t in transitions]
    data = [{
            'id': stage.id,
            'name': stage.name,
            'description': stage.description or ""
        } for stage in allowed_stages]
    return Response(data)

@api_view(['POST'])
@permission_classes([HasStagePermission])
def advance_application(request, application_id, stage_id):  # request is here
    application = _get_application_by_id(application_id)
    if not application:
        return Response({"detail": "Application not found"}, status=404)

    try:
        target_stage = application.workflow.stages.get(id=stage_id)
    except WorkflowStage.DoesNotExist:
        return Response({"detail": "Target stage does not exist"}, status=400)

    try:
        WorkflowService.advance_stage(
            application=application,
            user=request.user,
            target_stage=target_stage,
            context=request.data.get("context", {}),
            # remarks=request.data.get("remarks"),
        )
        # Pass the request.user down
        return _serialize_application(application, requesting_user=request.user)
    except Exception as e:
        return Response({"detail": str(e)}, status=400)

# ---------- REUSABLE: Raise Objection ----------
@api_view(['POST'])
@permission_classes([HasStagePermission])
def raise_objection(request, application_id):
    application = _get_application_by_id(application_id)
    if not application:
        return Response({"detail": "Application not found"}, status=status.HTTP_404_NOT_FOUND)

    objections = request.data.get("objections", [])
    if not objections:
        return Response({"detail": "objections list is required"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        target_stage = application.workflow.stages.get(name__icontains="objection")
    except WorkflowStage.DoesNotExist:
        return Response({"detail": "No objection stage defined"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        WorkflowService.raise_objection(
            application=application,
            user=request.user,
            target_stage=target_stage,
            objections=objections,
            remarks=request.data.get("remarks")
        )
    except Exception as e:
        return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    return _serialize_application(application)


# ---------- REUSABLE: Get Objections ----------
@api_view(['GET'])
@permission_classes([HasStagePermission])
def get_objections(request, application_id):
    application = _get_application_by_id(application_id)
    if not application:
        return Response({"detail": "Application not found"}, status=status.HTTP_404_NOT_FOUND)

    objections = Objection.objects.filter(
        content_type__model=application.__class__.__name__.lower(),
        object_id=application.pk
    ).order_by('-raised_on')

    serializer = WorkflowObjectionSerializer(objections, many=True)
    return Response(serializer.data)


# ---------- REUSABLE: Resolve Objections ----------
@api_view(['POST'])
@permission_classes([HasStagePermission])
def resolve_objections(request, application_id):
    application = _get_application_by_id(application_id)
    if not application:
        return Response({"detail": "Application not found"}, status=status.HTTP_404_NOT_FOUND)

    if request.user.role.name != "licensee":
        return Response({"detail": "Only licensee can resolve objections"}, status=status.HTTP_403_FORBIDDEN)

    unresolved = application.objections.filter(is_resolved=False)
    if unresolved.exists():
        return Response({"detail": "All objections must be resolved first"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        WorkflowService.resolve_objections(application, request.user)
    except Exception as e:
        return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    return _serialize_application(application)


# ---------- REUSABLE: Dashboard Counts ----------
@api_view(['GET'])
@permission_classes([HasStagePermission])
def dashboard_counts(request):
    models = [_get_model("license_application", "LicenseApplication"),
              _get_model("new_license_application", "NewLicenseApplication")]

    total = approved = pending = rejected = objection = 0

    for Model in models:
        if Model is None:
            continue
        qs = Model.objects
        total += qs.count()
        approved += qs.filter(current_stage__name='approved').count()
        rejected += qs.filter(current_stage__name__icontains='rejected').count()
        objection += qs.filter(current_stage__name__icontains='objection').count()
        pending += qs.filter(current_stage__name__in=['approved', 'rejected'] + [s for s in qs.values_list('current_stage__name', flat=True) if 'rejected' in s or 'objection' in s]).count()

    return Response({
        "total": total,
        "approved": approved,
        "rejected": rejected,
        "in_objection": objection,
        "pending": total - approved - rejected - objection
    })


# ---------- REUSABLE: Grouped Applications (by role) ----------
@api_view(['GET'])
@permission_classes([HasStagePermission])
def application_group(request):
    role_name = request.user.role.name if request.user.role else None
    if not role_name:
        return Response({"detail": "User has no role"}, status=400)

    models = [_get_model("license_application", "LicenseApplication"),
              _get_model("new_license_application", "NewLicenseApplication")]

    result = {"pending": [], "approved": [], "rejected": [], "objection": []}

    for Model in [m for m in models if m is not None]:
        qs = Model.objects.select_related('current_stage', 'workflow')

        if role_name == "licensee":
            result["applied"] = result.get("applied", []) + list(qs.filter(
                current_stage__name__in=['level_1', 'level_2', 'level_3', 'level_4', 'level_5']
            ))
            result["objection"] = result.get("objection", []) + list(qs.filter(
                current_stage__name__icontains='objection'
            ))
            result["pending"] = result.get("pending", []) + list(qs.filter(
                current_stage__name='awaiting_payment'
            ))
            result["approved"] = result.get("approved", []) + list(qs.filter(current_stage__name='approved'))
            result["rejected"] = result.get("rejected", []) + list(qs.filter(
                current_stage__name__icontains='rejected'
            ))

        elif role_name.startswith("level_"):
            level_num = role_name.replace("level_", "")  # "level_3" → "3"

            pending_stages = [role_name, f"{role_name}_objection"]
            rejected_stages = [f"rejected_by_{role_name}"]

            # Next level (e.g. level_1 approves → level_2)
            next_level = str(int(level_num) + 1)
            if level_num == "5":
                approved_stages = ["approved"]
            elif level_num == "2":
                approved_stages = ["level_3", "awaiting_payment"]  # special case
            else:
                approved_stages = [f"level_{next_level}"]

            result["pending"] += list(qs.filter(current_stage__name__in=pending_stages))
            result["approved"] += list(qs.filter(current_stage__name__in=approved_stages))
            result["rejected"] += list(qs.filter(current_stage__name__in=rejected_stages))  

    # Serialize using correct serializer per model
    serialized = {}
    for key, apps in result.items():
        serialized[key] = []
        for app in apps:
            serialized[key].append(_serialize_application(app).data)

    return Response(serialized)

def _get_application_by_id(application_id):
    """
    Find an application by application_id (string PK) in either:
      - license_application.LicenseApplication
      - new_license_application.NewLicenseApplication
    Returns the instance or None
    """
    model_configs = [
        ("license_application", "LicenseApplication"),
        ("new_license_application", "NewLicenseApplication"),
    ]

    for app_label, model_name in model_configs:
        try:
            Model = apps.get_model(app_label=app_label, model_name=model_name)
            # This will raise DoesNotExist if not found → we catch it
            return Model.objects.select_related('current_stage', 'workflow').get(
                application_id=application_id
            )
        except (LookupError, Model.DoesNotExist):
            continue  # Try next model

    return None


def _get_model(app_label, model_name):
    try:
        return apps.get_model(app_label, model_name)
    except LookupError:
        return None


# auth/workflow/views.py

from django.utils import timezone
from importlib import import_module
from rest_framework.response import Response

def _serialize_application(application, requesting_user=None):
    """
    Returns a proper DRF Response with serialized application data.
    Falls back gracefully if serializer is missing.
    """
    try:
        # Try to load the correct app-specific serializer
        module = import_module(f"{application._meta.app_label}.serializers")
        serializer_class = getattr(module, f"{application.__class__.__name__}Serializer")
        serializer = serializer_class(application)
        return Response(serializer.data)
    except (ImportError, AttributeError):
        # Graceful fallback — still returns full Response
        return Response({
            "application_id": application.application_id,
            "current_stage": application.current_stage.name if application.current_stage else "Unknown",
            "current_stage_id": application.current_stage.id if application.current_stage else None,
            "workflow": application.workflow.name,
            "status": "Stage advanced successfully",
            "advanced_by": requesting_user.username if requesting_user else "Unknown",
            "advanced_at": timezone.now().isoformat(),
            "note": "Full details unavailable — app-specific serializer not found."
        })