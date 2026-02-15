from django.utils import timezone
from django.db import transaction
from rest_framework.response import Response
from rest_framework.views import PermissionDenied
from django.apps import apps
from django.forms import ValidationError
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework import status
from importlib import import_module
from django.contrib.contenttypes.models import ContentType
from .models import Workflow, WorkflowStage, WorkflowTransition, StagePermission, Objection, Transaction
from .serializers import WorkflowSerializer, WorkflowStageSerializer, WorkflowTransitionSerializer, WorkflowObjectionSerializer, StagePermissionSerializer
from auth.roles.permissions import HasAppPermission
from .permissions import HasStagePermission
from .services import WorkflowService
from models.transactional.license_application.models import LicenseApplication
from models.transactional.new_license_application.models import NewLicenseApplication
from models.transactional.salesman_barman.models import SalesmanBarmanModel
from models.transactional.company_registration.models import CompanyModel
import logging

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
    application = _get_application_by_id(application_id)
    if not application:
        return Response({"detail": "Application not found"}, status=status.HTTP_404_NOT_FOUND)
        
    # Enforce stage-level processing permission for action discovery.
    # Without this, non-processing users can still fetch next actions on GET.
    if not request.user.is_superuser:
        if not getattr(request.user, 'role', None):
            return Response([], status=status.HTTP_200_OK)
        if not StagePermission.objects.filter(
            stage=application.current_stage,
            role=request.user.role,
            can_process=True
        ).exists():
            # For users who can view but not process this stage, return no actions
            # instead of 403 so frontend can render gracefully.
            return Response([], status=status.HTTP_200_OK)

    current_stage = application.current_stage
    transitions = WorkflowTransition.objects.filter(
        workflow=application.workflow,
        from_stage=current_stage
    ).select_related('to_stage')

    # Filter transitions by transition-level role condition when present.
    filtered_transitions = []
    for t in transitions:
        condition = t.condition or {}
        if WorkflowService._condition_role_matches(condition, request.user):
            filtered_transitions.append(t)

    data = []
    for t in filtered_transitions:
        action = str((t.condition or {}).get('action') or '').strip().upper()
        data.append({
            'id': t.to_stage.id,
            'name': t.to_stage.name,
            'description': t.to_stage.description or "",
            'action': action or None,
            'transition_id': t.id,
        })
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

    remarks = request.data.get("remarks", "")
    if not remarks and "context_data" in request.data:
                remarks = request.data["context_data"].get("remarks", "")
    
    try:
        WorkflowService.advance_stage(
            application=application,
            user=request.user,
            target_stage=target_stage,
            context=request.data.get("context_data", {}),
            remarks=remarks
        ) 
        # Pass the request.user down
        return _serialize_application(application, requesting_user=request.user)
    except Exception as e:
        return Response({"detail": str(e)}, status=400)

# ---------- REUSABLE: Raise Objection (FINAL WORKING VERSION) ----------
@api_view(['POST'])
@permission_classes([HasStagePermission])
def raise_objection(request, application_id):
    application = _get_application_by_id(application_id)
    if not application:
        return Response({"detail": "Application not found"}, status=status.HTTP_404_NOT_FOUND)

    target_stage_id = request.data.get("target_stage_id")
    objections = request.data.get("objections", [])
    remarks = request.data.get("remarks", "").strip()

    if not target_stage_id:
        return Response({"detail": "target_stage_id is required"}, status=status.HTTP_400_BAD_REQUEST)
    if not objections or not isinstance(objections, list):
        return Response({"detail": "objections must be a non-empty list"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        target_stage = WorkflowStage.objects.get(id=target_stage_id)
    except WorkflowStage.DoesNotExist:
        return Response({"detail": "Invalid target stage ID"}, status=status.HTTP_400_BAD_REQUEST)

    # Optional: extra safety — ensure the stage belongs to the same workflow
    if target_stage.workflow != application.workflow:
        return Response({"detail": "Target stage does not belong to this application workflow"}, status=400)

    try:
        with transaction.atomic():
            WorkflowService.raise_objection(
                application=application,
                user=request.user,
                target_stage=target_stage,
                objections=objections,
                remarks=remarks or "Objections raised"
            )

        return Response({
            "detail": "Objections raised successfully",
            "application_id": application.application_id,
            "current_stage": target_stage.name,
            "current_stage_id": target_stage.id,
            "objection_count": len(objections)
        }, status=status.HTTP_200_OK)

    except ValidationError as e:
        return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        return Response({"detail": f"Server error: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


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
        return Response({"detail": "Application not found"}, status=404)

    try:
        WorkflowService.resolve_objections(
            application=application,
            user=request.user,
            objection_ids=request.data.get("objection_ids"),
            updated_fields=request.data.get("updated_fields", {}),
            remarks=request.data.get("remarks")
        )
    except ValidationError as e:
        return Response({"detail": str(e)}, status=400)
    except PermissionDenied as e:
        return Response({"detail": str(e)}, status=403)

    return _serialize_application(application)


# ---------- REUSABLE: Dashboard Counts ----------
@api_view(['GET'])
@permission_classes([HasStagePermission])
def dashboard_counts(request):
    models = [_get_model("license_application", "LicenseApplication"),
              _get_model("new_license_application", "NewLicenseApplication"),
              _get_model("company_registration", "CompanyModel")]

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
              _get_model("new_license_application", "NewLicenseApplication"),
              _get_model("company_registration", "CompanyModel")]

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
        ("salesman_barman", "SalesmanBarmanModel"),
        ("company_registration", "CompanyModel"),
    ]

    for app_label, model_name in model_configs:
        try:
            Model = apps.get_model(app_label=app_label, model_name=model_name)
            field_names = {f.name for f in Model._meta.get_fields()}
            if 'application_id' in field_names:
                return Model.objects.select_related('current_stage', 'workflow').get(
                    application_id=application_id
                )
            if 'applicationId' in field_names:
                return Model.objects.select_related('current_stage', 'workflow').get(
                    applicationId=application_id
                )
        except LookupError:
            continue
        except Model.DoesNotExist:
            continue
        except Exception:
            continue

    return None

def _get_model(app_label, model_name):
    try:
        return apps.get_model(app_label, model_name)
    except LookupError:
        return None



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
        })
    
logger = logging.getLogger(__name__)

@api_view(['POST'])
def pay_license_fee(request, application_id):
   
    if not request.user.is_authenticated:
        return Response({"error": "Authentication required"}, status=status.HTTP_401_UNAUTHORIZED)

    if getattr(request.user, 'role', None) and request.user.role.name != 'licensee':
        return Response(
            {"error": "Only licensees can pay the license fee."},
            status=status.HTTP_403_FORBIDDEN
        )


    try:
        application = _get_application_by_id(application_id)
    except Exception as e:
        logger.error(f"Failed to resolve application {application_id}: {e}")
        return Response(
            {"error": "Application not found or invalid ID"},
            status=status.HTTP_404_NOT_FOUND
        )

    if not application:
        return Response({"error": "Application not found"}, status.HTTP_404_NOT_FOUND)

    # Must be in payment_pending stage
    if not hasattr(application, 'current_stage') or application.current_stage.name != 'payment_pending':
        return Response({
            "error": "Payment not allowed",
            "current_stage": getattr(application.current_stage, 'name', 'unknown'),
            "required_stage": "payment_pending"
        }, status=status.HTTP_400_BAD_REQUEST)

    # Verify user is the original applicant
    first_transaction = Transaction.objects.filter(
        content_type=ContentType.objects.get_for_model(application),
        object_id=str(application.pk)
    ).order_by('timestamp').first()

    if not first_transaction or first_transaction.performed_by != request.user:
        return Response(
            {"error": "You are not the applicant for this license."},
            status=status.HTTP_403_FORBIDDEN
        )

    # Get the 'approved' stage
    try:
        approved_stage = WorkflowStage.objects.get(
            workflow=application.workflow,
            name='approved'
        )
    except WorkflowStage.DoesNotExist:
        return Response(
            {"error": "Approved stage not configured."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

    # Advance to approved → triggers License creation via signal
    with transaction.atomic():
        WorkflowService.advance_stage(
            application=application,
            user=request.user,
            target_stage=approved_stage,
            remarks="License fee paid by applicant. License issued."
        )

    return Response({
        "success": True,
        "message": "Payment successful. License has been issued.",
        "application_id": application_id,
        "stage": "approved"
    }, status=status.HTTP_200_OK)

