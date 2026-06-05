from django.db import transaction
from django.forms import ValidationError
from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from django.core.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework import status
from auth.workflow.constants import WORKFLOW_IDS
from auth.roles.permissions import HasAppPermission
from auth.workflow.permissions import HasStagePermission
from auth.workflow.models import Workflow, StagePermission, WorkflowStage
from auth.workflow.services import WorkflowService
from models.transactional.helpers import _get_stage_sets, _normalize_role, _get_role_stage_names, _collect_reachable_stage_names
from .models import CompanyRegistration
from .serializers import CompanyRegistrationSerializer


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
        
        fin_year = CompanyRegistration.generate_fin_year()
        prefix = f"COMP/{fin_year}"
        last_app = CompanyRegistration.objects.filter(
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
        fresh = CompanyRegistration.objects.get(pk=application.pk)
        fresh_serializer = serializer_cls(fresh)
        return Response(fresh_serializer.data, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@parser_classes([MultiPartParser, FormParser, JSONParser])
@permission_classes([HasStagePermission])
def create_company_registration(request):
    return _create_application(request, "Company Registration", CompanyRegistrationSerializer)


@permission_classes([HasAppPermission('company_registration', 'view'), HasStagePermission])
@api_view(['GET'])
def list_company_registrations(request):
    role = request.user.role.name if request.user.role else None

    if role in ["single_window","site_admin"]:
        applications = CompanyRegistration.objects.all()
    elif role == "licensee":
        applications = CompanyRegistration.objects.filter(
            applicant=request.user,
            current_stage__name__in=[ "level_1", "awaiting_payment", "level_1_objection", "level_2_objection", "level_3_objection", "level_4_objection", "level_5_objection", "approved"]
        )
    else:
        applications = CompanyRegistration.objects.filter(
            current_stage__stagepermission__role=request.user.role,
            current_stage__stagepermission__can_process=True
        ).distinct()

    serializer = CompanyRegistrationSerializer(applications, many=True)
    return Response(serializer.data)


@permission_classes([HasAppPermission('company_registration', 'view')])
@api_view(['GET'])
def company_registration_detail(request, application_id):
    app = get_object_or_404(CompanyRegistration, application_id=application_id)
    serializer = CompanyRegistrationSerializer(app)
    return Response(serializer.data)



# Dashboard Counts
@permission_classes([HasAppPermission('company_registration', 'view')])
@api_view(['GET'])
def dashboard_counts(request):
    try:
        from models.masters.license.views import deactivate_all_expired_licenses
        deactivate_all_expired_licenses()
    except Exception:
        pass
    role = _normalize_role(request.user.role.name if request.user.role else None)
    workflow_id = WORKFLOW_IDS['COMPANY_REGISTRATION']
    stage_sets = _get_stage_sets(workflow_id)
    all_qs = CompanyRegistration.objects.all()

    if role == 'licensee':
        base_qs = CompanyRegistration.objects.filter(applicant=request.user)
        applied_stages = set(stage_sets['initial'])
        objection_stages = set(stage_sets['objection'])
        approved_stages = set(stage_sets['approved'])
        rejected_stages = set(stage_sets['rejected'])
        pending_stages = set(stage_sets['all']) - applied_stages - approved_stages - rejected_stages - objection_stages

        return Response({
            # Licensee UX: application is considered "Pending" until application-fee payment succeeds.
            "applied": base_qs.filter(current_stage__name__in=applied_stages).count(),
            "pending": base_qs.filter(current_stage__name__in=pending_stages).count(),
            "objection": base_qs.filter(current_stage__name__in=objection_stages).count(),
            "approved": base_qs.filter(current_stage__name__in=approved_stages).count(),
            "rejected": base_qs.filter(current_stage__name__in=rejected_stages).count(),
        })

    if role in ['site_admin', 'single_window']:
        applied_stages = set(stage_sets['initial'])
        objection_stages = set(stage_sets['objection'])
        approved_stages = set(stage_sets['approved'])
        rejected_stages = set(stage_sets['rejected'])
        pending_stages = set(stage_sets['all']) - applied_stages - approved_stages - rejected_stages - objection_stages

        return Response({
            "applied": all_qs.filter(current_stage__name__in=applied_stages).count(),
            "pending": all_qs.filter(current_stage__name__in=pending_stages).count(),
            "objection": all_qs.filter(current_stage__name__in=objection_stages).count(),
            "approved": all_qs.filter(current_stage__name__in=approved_stages).count(),
            "rejected": all_qs.filter(current_stage__name__in=rejected_stages).count(),
        })

    role_stage_names = _get_role_stage_names(request.user, workflow_id)
    if not role_stage_names:
        return Response({
            "pending": 0,
            "approved": 0,
            "rejected": 0,
        })

    role_objection_stages = set(stage_sets['objection'])
    pending_stages = set(role_stage_names) | role_objection_stages

    reachable_from_role = _collect_reachable_stage_names(workflow_id, set(role_stage_names))
    role_rejected_stages = set(stage_sets['rejected'])
    forward_stages = set(reachable_from_role) - pending_stages - role_rejected_stages

    return Response({
        "pending": all_qs.filter(current_stage__name__in=pending_stages).count(),
        "approved": all_qs.filter(current_stage__name__in=forward_stages).count(),
        "rejected": all_qs.filter(current_stage__name__in=role_rejected_stages).count(),
    })


@api_view(['GET'])
# @permission_classes([HasAppPermission('company_registration', 'view')])
@parser_classes([JSONParser])
def application_group(request):
    role = _normalize_role(request.user.role.name if request.user.role else None)
    workflow_id = WORKFLOW_IDS['COMPANY_REGISTRATION']
    stage_sets = _get_stage_sets(workflow_id)
    all_qs = CompanyRegistration.objects.all()

    if role == 'licensee':
        base_qs = CompanyRegistration.objects.filter(applicant=request.user)
        applied_stages = set(stage_sets['initial'])
        objection_stages = set(stage_sets['objection'])
        approved_stages = set(stage_sets['approved'])
        rejected_stages = set(stage_sets['rejected'])
        pending_stages = set(stage_sets['all']) - applied_stages - approved_stages - rejected_stages - objection_stages

        return Response({
            "applied": CompanyRegistrationSerializer(
                base_qs.filter(current_stage__name__in=applied_stages), many=True
            ).data,
            "pending": CompanyRegistrationSerializer(
                base_qs, many=True
            ).data,
            "objection": CompanyRegistrationSerializer(
                base_qs.filter(current_stage__name__in=objection_stages), many=True
            ).data,
            "approved": CompanyRegistrationSerializer(
                base_qs.filter(current_stage__name__in=approved_stages), many=True
            ).data,
            "rejected": CompanyRegistrationSerializer(
                base_qs.filter(current_stage__name__in=rejected_stages), many=True
            ).data
        })

    if role in ['site_admin', 'single_window']:
        
        applied_stages = set(stage_sets['initial'])
        objection_stages = set(stage_sets['objection'])
        approved_stages = set(stage_sets['approved'])
        rejected_stages = set(stage_sets['rejected'])
        pending_stages = set(stage_sets['all']) - applied_stages - approved_stages - rejected_stages - objection_stages

        return Response({
            "applied": CompanyRegistrationSerializer(
                all_qs.filter(current_stage__name__in=applied_stages), many=True
            ).data,
            "pending": CompanyRegistrationSerializer(
                all_qs.filter(current_stage__name__in=pending_stages), many=True
            ).data,
            "objection": CompanyRegistrationSerializer(
                all_qs.filter(current_stage__name__in=objection_stages), many=True
            ).data,
            "approved": CompanyRegistrationSerializer(
                all_qs.filter(current_stage__name__in=approved_stages), many=True
            ).data,
            "rejected": CompanyRegistrationSerializer(
                all_qs.filter(current_stage__name__in=rejected_stages), many=True
            ).data
        })

    role_stage_names = _get_role_stage_names(request.user, workflow_id)
    if role_stage_names:
        
        role_objection_stages = set(stage_sets['objection'])
        pending_stages = set(role_stage_names) | role_objection_stages
        reachable_from_role = _collect_reachable_stage_names(workflow_id, set(role_stage_names))
        role_rejected_stages = set(stage_sets['rejected'])
        forward_stages = set(reachable_from_role) - pending_stages - role_rejected_stages

        return Response({
            "applied": [],
            "pending": CompanyRegistrationSerializer(
                all_qs.filter(current_stage__name__in=pending_stages), many=True
            ).data,
            "objection": CompanyRegistrationSerializer(
                all_qs.filter(current_stage__name__in=role_objection_stages), many=True
            ).data,
            "approved": CompanyRegistrationSerializer(
                all_qs.filter(current_stage__name__in=forward_stages), many=True
            ).data,
            "rejected": CompanyRegistrationSerializer(
                all_qs.filter(current_stage__name__in=role_rejected_stages), many=True
            ).data
        })

    return Response({
        "applied": [],
        "pending": [],
        "objection": [],
        "approved": [],
        "rejected": []
    })

