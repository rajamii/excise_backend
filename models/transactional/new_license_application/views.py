from django.shortcuts import get_object_or_404
from datetime import date, timedelta
from django.db import transaction
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.response import Response
from rest_framework import status
from auth.roles.permissions import HasAppPermission
from auth.workflow.permissions import HasStagePermission
from auth.workflow.services import WorkflowService
from auth.workflow.models import Workflow
from auth.workflow.constants import WORKFLOW_IDS
from .models import NewLicenseApplication
from models.masters.license.models import License
from .serializers import NewLicenseApplicationSerializer, ObjectionSerializer, ResolveObjectionSerializer
from auth.workflow.models import WorkflowStage, WorkflowTransition, Objection
from django.core.exceptions import ValidationError, PermissionDenied
from django.utils import timezone
import re


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


def _extract_level_index(stage_name):
    if not stage_name:
        return None
    match = re.match(r'^level_(\d+)$', str(stage_name).strip().lower())
    return int(match.group(1)) if match else None


def _get_stage_sets(workflow_id: int):
    stages = WorkflowStage.objects.filter(workflow_id=workflow_id)
    stage_names = set(stages.values_list('name', flat=True))
    level_stage_names = sorted(
        [name for name in stage_names if _extract_level_index(name) is not None],
        key=lambda name: _extract_level_index(name) or 0
    )
    level_indexes = {name: _extract_level_index(name) for name in level_stage_names}
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
        'level': set(level_stage_names),
        'level_ordered': level_stage_names,
        'level_indexes': level_indexes,
        'objection': objection_stage_names,
        'rejected': rejected_stage_names,
        'approved': approved_stage_names,
        'payment': payment_stage_names,
        'initial': initial_stage_names,
    }


def _get_role_stage_names(user, workflow_id: int):
    role = getattr(user, 'role', None)
    if not role:
        return set()
    return set(
        WorkflowStage.objects.filter(
            workflow_id=workflow_id,
            stagepermission__role=role,
            stagepermission__can_process=True
        ).values_list('name', flat=True).distinct()
    )


def _collect_reachable_stage_names(workflow_id: int, start_stage_names: set[str]):
    if not start_stage_names:
        return set()

    edges = {}
    for from_name, to_name in WorkflowTransition.objects.filter(workflow_id=workflow_id).values_list(
        'from_stage__name', 'to_stage__name'
    ):
        edges.setdefault(from_name, set()).add(to_name)

    visited = set(start_stage_names)
    stack = list(start_stage_names)
    while stack:
        current = stack.pop()
        for nxt in edges.get(current, set()):
            if nxt not in visited:
                visited.add(nxt)
                stack.append(nxt)
    return visited


def _create_application(request, workflow_id: int, serializer_cls):
   
    serializer = serializer_cls(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    with transaction.atomic():
        
        workflow = get_object_or_404(Workflow, id=workflow_id)
        
        try:
            initial_stage = workflow.stages.get(is_initial=True)
        except WorkflowStage.DoesNotExist:
            return Response(
                {"detail": "Workflow has no initial stage (is_initial=True)."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        
        district_code = serializer.validated_data['site_district'].district_code
        prefix = f"NLI/{district_code}/{NewLicenseApplication.generate_fin_year()}"
        last_app = NewLicenseApplication.objects.filter(
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
       
        WorkflowService.submit_application(
            application=application,
            user=request.user,
            remarks="Application submitted"
        )

        fresh = NewLicenseApplication.objects.get(pk=application.pk)
        fresh_serializer = serializer_cls(fresh)
        return Response(fresh_serializer.data, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@parser_classes([MultiPartParser, FormParser, JSONParser])
@permission_classes([HasStagePermission])
def create_new_license_application(request):
    return _create_application(request, WORKFLOW_IDS['LICENSE_APPROVAL'], NewLicenseApplicationSerializer)


@api_view(['POST'])
@permission_classes([HasStagePermission])
def initiate_renewal(request, license_id):
    """
    Initiate renewal by creating a pre-filled new application from an existing license.
    """
    old_license = get_object_or_404(License, license_id=license_id, source_type='new_license_application')

    old_app = old_license.source_application
    if not isinstance(old_app, NewLicenseApplication):
        return Response({"detail": "Invalid license source."}, status=status.HTTP_400_BAD_REQUEST)

    if old_app.applicant != request.user:
        return Response({"detail": "You can only renew your own license."}, status=status.HTTP_403_FORBIDDEN)

    today = date.today()
    if old_license.valid_up_to > today + timedelta(days=90):
        return Response({
            "detail": f"Renewal not allowed yet. License valid until {old_license.valid_up_to.strftime('%d/%m/%Y')}. "
                     "You can renew within the last 90 days or after expiry."
        }, status=status.HTTP_400_BAD_REQUEST)

    # Build pre-filled data
    new_data = {
        'license_type': old_app.license_type,
        'license_category': old_app.license_category,
        'license_sub_category': old_app.license_sub_category,
        'establishment_name': old_app.establishment_name,
        'site_type': old_app.site_type,
        'applicant_name': old_app.applicant_name,
        'father_husband_name': old_app.father_husband_name,
        'dob': old_app.dob,
        'gender': old_app.gender,
        'nationality': old_app.nationality,
        'residential_status': old_app.residential_status,
        'present_address': old_app.present_address,
        'permanent_address': old_app.permanent_address,
        'pan': old_app.pan,
        'email': old_app.email,
        'mobile_number': old_app.mobile_number,
        'mode_of_operation': old_app.mode_of_operation,
        'site_district': old_app.site_district,
        'site_subdivision': old_app.site_subdivision,
        'road_name': old_app.road_name,
        'ward_name': old_app.ward_name,
        'police_station': old_app.police_station,
        'pin_code': old_app.pin_code,
        'company_name': old_app.company_name,
        'company_pan': old_app.company_pan,
        'company_cin': old_app.company_cin,
        'company_email': old_app.company_email,
        'company_phone_number': old_app.company_phone_number,
    }

    # Manual creation
    district_code = str(old_app.site_district.district_code)
    fin_year = NewLicenseApplication.generate_fin_year()
    prefix = f"NLI/{district_code}/{fin_year}"

    with transaction.atomic():
        last_app = NewLicenseApplication.objects.filter(
            application_id__startswith=prefix
        ).select_for_update().order_by('-application_id').first()

        last_number = int(last_app.application_id.split('/')[-1]) if last_app else 0
        new_number = str(last_number + 1).zfill(4)
        new_application_id = f"{prefix}/{new_number}"

        workflow = get_object_or_404(Workflow, id=WORKFLOW_IDS['LICENSE_APPROVAL'])
        initial_stage = workflow.stages.get(is_initial=True)

        new_application = NewLicenseApplication.objects.create(
            application_id=new_application_id,
            workflow=workflow,
            current_stage=initial_stage,
            applicant=request.user,
            renewal_of=old_license,
            **new_data,
        )

    WorkflowService.submit_application(
        application=new_application,
        user=request.user,
        remarks="Renewal application auto-submitted"
    )

    serializer = NewLicenseApplicationSerializer(new_application)
    return Response({
        "detail": "Renewal application initiated and submitted successfully.",
        "application": serializer.data
    }, status=status.HTTP_201_CREATED)


@permission_classes([HasAppPermission('new_license_application', 'view'), HasStagePermission])
@api_view(['GET'])
def list_license_applications(request):
    role = _normalize_role(request.user.role.name if request.user.role else None)

    if role in ["single_window","site_admin"]:
        applications = NewLicenseApplication.objects.all()
    elif role == "licensee":
        applications = NewLicenseApplication.objects.filter(applicant=request.user)
    else:
        applications = NewLicenseApplication.objects.filter(
            current_stage__stagepermission__role=request.user.role,
            current_stage__stagepermission__can_process=True
        ).distinct()

    serializer = NewLicenseApplicationSerializer(applications, many=True)
    return Response(serializer.data)


# License Application Detail
@permission_classes([HasAppPermission('new_license_application', 'view'), HasStagePermission])
@api_view(['GET'])
def license_application_detail(request, pk):
    application = get_object_or_404(NewLicenseApplication, pk=pk)
    serializer = NewLicenseApplicationSerializer(application)
    return Response(serializer.data)


# Print License View
@permission_classes([HasAppPermission('new_license_application', 'update')])
@api_view(['POST'])
@parser_classes([JSONParser])
def print_license_view(request, application_id):
    license = get_object_or_404(NewLicenseApplication, application_id=application_id)

    if not license.is_approved:
        return Response({"error": "License is not approved yet."}, status=403)

    can_print, fee = license.can_print_license()

    if not can_print:
        return Response({
            "error": "Print limit exceeded. Please pay ₹500 to continue printing.",
            "fee_required": fee
        }, status=403)

    if fee > 0 and not license.is_print_fee_paid:
        return Response({"error": "₹500 fee not paid yet."}, status=403)

    license.record_license_print(fee_paid=(fee > 0))

    return Response({
        "success": "License printed.",
        "print_count": license.print_count
    })

# Dashboard Counts
@permission_classes([HasAppPermission('new_license_application', 'view'), HasStagePermission])
@api_view(['GET'])
def dashboard_counts(request):
    role = _normalize_role(request.user.role.name if request.user.role else None)
    workflow_id = WORKFLOW_IDS['LICENSE_APPROVAL']
    stage_sets = _get_stage_sets(workflow_id)
    all_qs = NewLicenseApplication.objects.all()

    if role == 'licensee':
        base_qs = NewLicenseApplication.objects.filter(applicant=request.user)
        applied_stages = set(stage_sets['initial'])
        objection_stages = set(stage_sets['objection'])
        approved_stages = set(stage_sets['approved'])
        rejected_stages = set(stage_sets['rejected'])
        pending_stages = set(stage_sets['all']) - applied_stages - approved_stages - rejected_stages - objection_stages

        return Response({
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
        return Response({"detail": "Invalid role"}, status=status.HTTP_400_BAD_REQUEST)

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

# Application Grouping
@permission_classes([HasAppPermission('new_license_application', 'view'), HasStagePermission])
@api_view(['GET'])
@parser_classes([JSONParser])
def application_group(request):
    role = _normalize_role(request.user.role.name if request.user.role else None)
    workflow_id = WORKFLOW_IDS['LICENSE_APPROVAL']
    stage_sets = _get_stage_sets(workflow_id)
    all_qs = NewLicenseApplication.objects.all()

    if role == 'licensee':
        base_qs = NewLicenseApplication.objects.filter(applicant=request.user)
        applied_stages = set(stage_sets['initial'])
        objection_stages = set(stage_sets['objection'])
        approved_stages = set(stage_sets['approved'])
        rejected_stages = set(stage_sets['rejected'])
        pending_stages = set(stage_sets['all']) - applied_stages - approved_stages - rejected_stages - objection_stages

        return Response({
            "applied": NewLicenseApplicationSerializer(
                base_qs.filter(current_stage__name__in=applied_stages), many=True
            ).data,
            "pending": NewLicenseApplicationSerializer(
                base_qs.filter(current_stage__name__in=pending_stages), many=True
            ).data,
            "objection": NewLicenseApplicationSerializer(
                base_qs.filter(current_stage__name__in=objection_stages), many=True
            ).data,
            "approved": NewLicenseApplicationSerializer(
                base_qs.filter(current_stage__name__in=approved_stages), many=True
            ).data,
            "rejected": NewLicenseApplicationSerializer(
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
            "applied": NewLicenseApplicationSerializer(
                all_qs.filter(current_stage__name__in=applied_stages), many=True
            ).data,
            "pending": NewLicenseApplicationSerializer(
                all_qs.filter(current_stage__name__in=pending_stages), many=True
            ).data,
            "objection": NewLicenseApplicationSerializer(
                all_qs.filter(current_stage__name__in=objection_stages), many=True
            ).data,
            "approved": NewLicenseApplicationSerializer(
                all_qs.filter(current_stage__name__in=approved_stages), many=True
            ).data,
            "rejected": NewLicenseApplicationSerializer(
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
            "pending": NewLicenseApplicationSerializer(
                all_qs.filter(current_stage__name__in=pending_stages), many=True
            ).data,
            "objection": NewLicenseApplicationSerializer(
                all_qs.filter(current_stage__name__in=role_objection_stages), many=True
            ).data,
            "approved": NewLicenseApplicationSerializer(
                all_qs.filter(current_stage__name__in=forward_stages), many=True
            ).data,
            "rejected": NewLicenseApplicationSerializer(
                all_qs.filter(current_stage__name__in=role_rejected_stages), many=True
            ).data
        })

    return Response({"detail": "Invalid role"}, status=status.HTTP_400_BAD_REQUEST)
