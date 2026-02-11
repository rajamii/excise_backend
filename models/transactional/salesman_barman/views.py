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
from auth.workflow.constants import WORKFLOW_IDS
from auth.workflow.services import WorkflowService
from models.masters.license.models import License
from .models import SalesmanBarmanModel
from .serializers import SalesmanBarmanSerializer
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

def _create_application(request, workflow_id: int, serializer_cls):
    
    serializer = serializer_cls(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    with transaction.atomic():
        
        # 1. Workflow & initial stage
        workflow = get_object_or_404(Workflow, id=workflow_id)
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
    return _create_application(request, WORKFLOW_IDS['SALESMAN_BARMAN'], SalesmanBarmanSerializer)


@api_view(['POST'])
@permission_classes([HasStagePermission])
def initiate_renewal(request, license_id):
    """
    Initiate renewal by creating a pre-filled new application from an existing license.
    """
    old_license = get_object_or_404(License, license_id=license_id, source_type='salesman_barman')

    old_app = old_license.source_application
    if not isinstance(old_app, SalesmanBarmanModel):
        return Response({"detail": "Invalid license source."}, status=status.HTTP_400_BAD_REQUEST)

    if old_app.applicant != request.user:
        return Response({"detail": "You can only renew your own license."}, status=status.HTTP_403_FORBIDDEN)

    # Optional early renewal restriction (adjust or remove as needed)
    from datetime import date, timedelta
    today = date.today()
    if old_license.valid_up_to > today + timedelta(days=90):  # More than 90 days left
        return Response({
            "detail": f"Renewal not allowed yet. License valid until {old_license.valid_up_to.strftime('%d/%m/%Y')}. "
                     "You can renew within the last 90 days or after expiry."
        }, status=status.HTTP_400_BAD_REQUEST)

    # Build pre-filled data
    new_data = {
        'role': old_app.role,
        'firstName': old_app.firstName,
        'middleName': old_app.middleName or '',
        'lastName': old_app.lastName,
        'fatherHusbandName': old_app.fatherHusbandName,
        'gender': old_app.gender,
        'dob': old_app.dob.strftime('%Y-%m-%d'),
        'nationality': old_app.nationality,
        'address': old_app.address,
        'pan': old_app.pan,
        'aadhaar': old_app.aadhaar,
        'mobileNumber': old_app.mobileNumber,
        'emailId': old_app.emailId or '',
        'sikkimSubject': old_app.sikkimSubject,
        'excise_district': old_app.excise_district,
        'license_category': old_app.license_category,
        'license': old_app.license,
    }

    # Generate application_id manually
    district_code = str(old_app.excise_district.district_code)
    fin_year = SalesmanBarmanModel.generate_fin_year()
    prefix = f"SBM/{district_code}/{fin_year}"

    with transaction.atomic():
        last_app = SalesmanBarmanModel.objects.filter(
            application_id__startswith=prefix
        ).select_for_update().order_by('-application_id').first()

        last_number = int(last_app.application_id.split('/')[-1]) if last_app else 0
        new_number = str(last_number + 1).zfill(4)
        new_application_id = f"{prefix}/{new_number}"

        # Get workflow and initial stage
        workflow = get_object_or_404(Workflow, id=WORKFLOW_IDS['SALESMAN_BARMAN'])
        initial_stage = workflow.stages.get(is_initial=True)

        # Create the application instance directly
        new_application = SalesmanBarmanModel.objects.create(
            application_id=new_application_id,
            workflow=workflow,
            current_stage=initial_stage,
            applicant=request.user,
            renewal_of=old_license,
            **new_data,
            passPhoto=old_app.passPhoto,
            aadhaarCard=old_app.aadhaarCard,
            residentialCertificate=old_app.residentialCertificate,
            dateofBirthProof=old_app.dateofBirthProof,
        )

    # Log submission transaction
    WorkflowService.submit_application(
        application=new_application,
        user=request.user,
        remarks="Renewal application auto-submitted (pre-filled from previous license)"
    )

    # Return fresh serialized data
    serializer = SalesmanBarmanSerializer(new_application)
    return Response({
        "detail": "Renewal application initiated and submitted successfully.",
        "application": serializer.data
    }, status=status.HTTP_201_CREATED)


@permission_classes([HasAppPermission('license_application', 'view'), HasStagePermission])
@api_view(['GET'])
def list_salesman_barman(request):
    role = _normalize_role(request.user.role.name if request.user.role else None)

    if role in ["single_window","site_admin"]:
        applications = SalesmanBarmanModel.objects.all()
    elif role == "licensee":
        applications = SalesmanBarmanModel.objects.filter(applicant=request.user)
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
    role = _normalize_role(request.user.role.name if request.user.role else None)
    workflow_id = WORKFLOW_IDS['SALESMAN_BARMAN']
    stage_sets = _get_stage_sets(workflow_id)
    all_qs = SalesmanBarmanModel.objects.all()

    if role == 'licensee':
        base_qs = SalesmanBarmanModel.objects.filter(applicant=request.user)
        applied_stages = stage_sets['initial'] | stage_sets['level']
        pending_stages = stage_sets['objection'] | stage_sets['payment']
        return Response({
            "applied": base_qs.filter(current_stage__name__in=applied_stages).count(),
            "pending": base_qs.filter(current_stage__name__in=pending_stages).count(),
            "approved": base_qs.filter(current_stage__name__in=stage_sets['approved'], is_approved=True).count(),
            "rejected": base_qs.filter(current_stage__name__in=stage_sets['rejected']).count(),
        })

    if role in ['site_admin', 'single_window']:
        applied_stages = stage_sets['initial'] | stage_sets['level']
        pending_stages = stage_sets['objection'] | stage_sets['payment']
        return Response({
            "applied": all_qs.filter(current_stage__name__in=applied_stages).count(),
            "pending": all_qs.filter(current_stage__name__in=pending_stages).count(),
            "approved": all_qs.filter(current_stage__name__in=stage_sets['approved'], is_approved=True).count(),
            "rejected": all_qs.filter(current_stage__name__in=stage_sets['rejected']).count(),
        })

    role_stage_names = _get_role_stage_names(request.user, workflow_id)
    if not role_stage_names:
        return Response({"detail": "Invalid role"}, status=status.HTTP_400_BAD_REQUEST)

    role_level_indexes = [
        stage_sets['level_indexes'][name]
        for name in role_stage_names
        if name in stage_sets['level_indexes']
    ]
    max_role_level = max(role_level_indexes) if role_level_indexes else None

    role_objection_stages = set()
    for stage_name in role_stage_names:
        index = _extract_level_index(stage_name)
        candidate = f'level_{index}_objection' if index else None
        if candidate and candidate in stage_sets['all']:
            role_objection_stages.add(candidate)

    forward_stages = set(stage_sets['approved']) | set(stage_sets['payment'])
    if max_role_level is not None:
        forward_stages.update({
            name for name, idx in stage_sets['level_indexes'].items()
            if idx and idx > max_role_level
        })

    role_rejected_stages = {
        f'rejected_by_{stage_name}'
        for stage_name in role_stage_names
        if f'rejected_by_{stage_name}' in stage_sets['all']
    }
    if 'rejected' in stage_sets['all']:
        role_rejected_stages.add('rejected')

    return Response({
        "pending": all_qs.filter(current_stage__name__in=(role_stage_names | role_objection_stages)).count(),
        "approved": all_qs.filter(current_stage__name__in=forward_stages).count(),
        "rejected": all_qs.filter(current_stage__name__in=role_rejected_stages).count(),
    })

@permission_classes([HasAppPermission('license_application', 'view'), HasStagePermission])
@api_view(['GET'])
@parser_classes([JSONParser])
def application_group(request):
    role = _normalize_role(request.user.role.name if request.user.role else None)
    workflow_id = WORKFLOW_IDS['SALESMAN_BARMAN']
    stage_sets = _get_stage_sets(workflow_id)
    all_qs = SalesmanBarmanModel.objects.all()

    if role == 'licensee':
        base_qs = SalesmanBarmanModel.objects.filter(applicant=request.user)
        applied_stages = stage_sets['initial'] | stage_sets['level']
        pending_stages = stage_sets['objection'] | stage_sets['payment']
        result = {
            "applied": SalesmanBarmanSerializer(
                base_qs.filter(current_stage__name__in=applied_stages),
                many=True
            ).data,
            "pending": SalesmanBarmanSerializer(
                base_qs.filter(current_stage__name__in=pending_stages),
                many=True
            ).data,
            "approved": SalesmanBarmanSerializer(
                base_qs.filter(current_stage__name__in=stage_sets['approved']),
                many=True
            ).data,
            "rejected": SalesmanBarmanSerializer(
                base_qs.filter(current_stage__name__in=stage_sets['rejected']),
                many=True
            ).data
        }
        return Response(result)

    if role in ['site_admin', 'single_window']:
        applied_stages = stage_sets['initial'] | stage_sets['level']
        pending_stages = stage_sets['objection'] | stage_sets['payment']
        return Response({
            "applied": SalesmanBarmanSerializer(
                all_qs.filter(current_stage__name__in=applied_stages), many=True
            ).data,
            "pending": SalesmanBarmanSerializer(
                all_qs.filter(current_stage__name__in=pending_stages), many=True
            ).data,
            "approved": SalesmanBarmanSerializer(
                all_qs.filter(current_stage__name__in=stage_sets['approved']), many=True
            ).data,
            "rejected": SalesmanBarmanSerializer(
                all_qs.filter(current_stage__name__in=stage_sets['rejected']), many=True
            ).data
        })

    role_stage_names = _get_role_stage_names(request.user, workflow_id)
    if role_stage_names:
        role_level_indexes = [
            stage_sets['level_indexes'][name]
            for name in role_stage_names
            if name in stage_sets['level_indexes']
        ]
        max_role_level = max(role_level_indexes) if role_level_indexes else None

        role_objection_stages = set()
        for stage_name in role_stage_names:
            index = _extract_level_index(stage_name)
            candidate = f'level_{index}_objection' if index else None
            if candidate and candidate in stage_sets['all']:
                role_objection_stages.add(candidate)

        forward_stages = set(stage_sets['approved']) | set(stage_sets['payment'])
        if max_role_level is not None:
            forward_stages.update({
                name for name, idx in stage_sets['level_indexes'].items()
                if idx and idx > max_role_level
            })

        role_rejected_stages = {
            f'rejected_by_{stage_name}'
            for stage_name in role_stage_names
            if f'rejected_by_{stage_name}' in stage_sets['all']
        }
        if 'rejected' in stage_sets['all']:
            role_rejected_stages.add('rejected')

        return Response({
            "pending": SalesmanBarmanSerializer(
                all_qs.filter(current_stage__name__in=(role_stage_names | role_objection_stages)), many=True
            ).data,
            "approved": SalesmanBarmanSerializer(
                all_qs.filter(current_stage__name__in=forward_stages), many=True
            ).data,
            "rejected": SalesmanBarmanSerializer(
                all_qs.filter(current_stage__name__in=role_rejected_stages), many=True
            ).data
        })

    return Response({"detail": "Invalid role"}, status=status.HTTP_400_BAD_REQUEST)
