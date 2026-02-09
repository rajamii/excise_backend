from django.shortcuts import get_object_or_404
from datetime import date, timedelta
from django.db import transaction
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.parsers import JSONParser, MultiPartParser, FormParser
from rest_framework.response import Response
from auth.roles.permissions import HasAppPermission
from .models import LicenseApplication
from models.masters.license.models import License
from models.masters.core.models import LocationFee
from .serializers import LicenseApplicationSerializer, LocationFeeSerializer
from rest_framework import status
from auth.workflow.models import Workflow, StagePermission, WorkflowStage
from auth.workflow.constants import WORKFLOW_IDS
from auth.workflow.permissions import HasStagePermission
from auth.workflow.services import WorkflowService
import re


def _normalize_role(role_name):
    if not role_name:
        return None
    normalized = str(role_name).strip().lower().replace('-', '_').replace(' ', '_')
    aliases = {
        'license_user': 'licensee',
        'licensee_user': 'licensee',
        'permit_section': 'permit_section',
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
        workflow = get_object_or_404(Workflow, id=workflow_id)
        initial_stage = workflow.stages.get(is_initial=True)
        district_code = serializer.validated_data['excise_district'].district_code

        # Lock rows with same prefix and get the last number
        prefix = f"LIC/{district_code}/{LicenseApplication.generate_fin_year()}"
        last_app = LicenseApplication.objects.filter(
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

        sp = StagePermission.objects.filter(stage=initial_stage, can_process=True).first()
        if not sp or not sp.role:
            return Response(
                {"detail": "No role assigned to process the initial stage."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        WorkflowService.submit_application(
            application=application,
            user=request.user,
            remarks="Application submitted",
        )

        fresh = LicenseApplication.objects.get(pk=application.pk)
        fresh_serializer = serializer_cls(fresh)
        return Response(fresh_serializer.data, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@parser_classes([MultiPartParser, FormParser, JSONParser])
@permission_classes([HasStagePermission])
def create_license_application(request):
    return _create_application(request, WORKFLOW_IDS['LICENSE_APPROVAL'], LicenseApplicationSerializer)


@api_view(['POST'])
@permission_classes([HasStagePermission])
def initiate_renewal(request, license_id):
    """
    Initiate renewal by creating a pre-filled new application from an existing license.
    """
    old_license = get_object_or_404(License, license_id=license_id, source_type='license_application')

    old_app = old_license.source_application
    if not isinstance(old_app, LicenseApplication):
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
        'excise_district': old_app.excise_district,
        'license_category': old_app.license_category,
        'excise_subdivision': old_app.excise_subdivision,
        'license': old_app.license,
        'license_type': old_app.license_type,
        'establishment_name': old_app.establishment_name,
        'mobile_number': old_app.mobile_number,
        'email': old_app.email,
        'license_no': old_app.license_no,
        'initial_grant_date': old_app.initial_grant_date,
        'renewed_from': old_app.renewed_from,
        'valid_up_to': old_app.valid_up_to,
        'yearly_license_fee': old_app.yearly_license_fee,
        'license_nature': old_app.license_nature,
        'functioning_status': old_app.functioning_status,
        'mode_of_operation': old_app.mode_of_operation,
        'site_subdivision': old_app.site_subdivision,
        'police_station': old_app.police_station,
        'location_category': old_app.location_category,
        'location_name': old_app.location_name,
        'ward_name': old_app.ward_name,
        'business_address': old_app.business_address,
        'road_name': old_app.road_name,
        'pin_code': old_app.pin_code,
        'latitude': old_app.latitude,
        'longitude': old_app.longitude,
        'company_name': old_app.company_name,
        'company_address': old_app.company_address,
        'company_pan': old_app.company_pan,
        'company_cin': old_app.company_cin,
        'incorporation_date': old_app.incorporation_date,
        'company_phone_number': old_app.company_phone_number,
        'company_email': old_app.company_email,
        'status' : old_app.status,
        'member_name': old_app.member_name,
        'father_husband_name': old_app.father_husband_name,
        'nationality': old_app.nationality,
        'gender': old_app.gender,
        'pan': old_app.pan,
        'member_mobile_number': old_app.member_mobile_number,
        'member_email': old_app.member_email,
        'photo': old_app.photo,
    }

    # Manual creation to handle files/IDs
    district_code = str(old_app.excise_district.district_code)
    fin_year = LicenseApplication.generate_fin_year()
    prefix = f"LIC/{district_code}/{fin_year}"

    with transaction.atomic():
        last_app = LicenseApplication.objects.filter(
            application_id__startswith=prefix
        ).select_for_update().order_by('-application_id').first()

        last_number = int(last_app.application_id.split('/')[-1]) if last_app else 0
        new_number = str(last_number + 1).zfill(4)
        new_application_id = f"{prefix}/{new_number}"

        workflow = get_object_or_404(Workflow, id=WORKFLOW_IDS['LICENSE_APPROVAL'])
        initial_stage = workflow.stages.get(is_initial=True)

        new_application = LicenseApplication.objects.create(
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
        remarks="Renewal application"
    )

    serializer = LicenseApplicationSerializer(new_application)
    return Response({
        "detail": "Renewal application initiated and submitted successfully.",
        "application": serializer.data
    }, status=status.HTTP_201_CREATED)


@permission_classes([HasAppPermission('license_application', 'view'), HasStagePermission])
@api_view(['GET'])
def list_license_applications(request):
    role = _normalize_role(request.user.role.name if request.user.role else None)

    if role in ["single_window","site_admin"]:
        applications = LicenseApplication.objects.all()
    elif role == "licensee":
        applications = LicenseApplication.objects.filter(applicant=request.user)
    else:
        applications = LicenseApplication.objects.filter(
            current_stage__stagepermission__role=request.user.role,
            current_stage__stagepermission__can_process=True
        ).distinct()

    serializer = LicenseApplicationSerializer(applications, many=True)
    return Response(serializer.data)


@permission_classes([HasAppPermission('license_application', 'view'), HasStagePermission])
@api_view(['GET'])
def license_application_detail(request, pk):
    application = get_object_or_404(LicenseApplication, pk=pk)
    serializer = LicenseApplicationSerializer(application)
    return Response(serializer.data)


@permission_classes([HasAppPermission('license_application', 'update')])
@api_view(['POST'])
@parser_classes([JSONParser])
def print_license_view(request, application_id):
    license = get_object_or_404(LicenseApplication, application_id=application_id)

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

@permission_classes([HasAppPermission('license_application', 'view')])
@api_view(['GET'])
def get_location_fees(request):
    fees = LocationFee.objects.all()
    serializer = LocationFeeSerializer(fees, many=True)
    return Response(serializer.data)


@permission_classes([HasAppPermission('license_application', 'view'), HasStagePermission])
@api_view(['GET'])
def dashboard_counts(request):
    role = _normalize_role(request.user.role.name if request.user.role else None)
    workflow_id = WORKFLOW_IDS['LICENSE_APPROVAL']
    stage_sets = _get_stage_sets(workflow_id)
    all_qs = LicenseApplication.objects.all()

    if role == 'licensee':
        base_qs = LicenseApplication.objects.filter(applicant=request.user)
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
    workflow_id = WORKFLOW_IDS['LICENSE_APPROVAL']
    stage_sets = _get_stage_sets(workflow_id)
    all_qs = LicenseApplication.objects.all()

    if role == 'licensee':
        base_qs = LicenseApplication.objects.filter(applicant=request.user)
        applied_stages = stage_sets['initial'] | stage_sets['level']
        pending_stages = stage_sets['objection'] | stage_sets['payment']
        result = {
            "applied": LicenseApplicationSerializer(
               base_qs.filter(current_stage__name__in=applied_stages),
                many=True
            ).data,
            "pending": LicenseApplicationSerializer(
                base_qs.filter(current_stage__name__in=pending_stages),
                many=True
            ).data,
            "approved": LicenseApplicationSerializer(
                base_qs.filter(current_stage__name__in=stage_sets['approved']),
                many=True
            ).data,
            "rejected": LicenseApplicationSerializer(
                base_qs.filter(current_stage__name__in=stage_sets['rejected']),
                many=True
            ).data
        }
        return Response(result)

    if role in ['site_admin', 'single_window']:
        applied_stages = stage_sets['initial'] | stage_sets['level']
        pending_stages = stage_sets['objection'] | stage_sets['payment']
        return Response({
            "applied": LicenseApplicationSerializer(
                all_qs.filter(current_stage__name__in=applied_stages), many=True
            ).data,
            "pending": LicenseApplicationSerializer(
                all_qs.filter(current_stage__name__in=pending_stages), many=True
            ).data,
            "approved": LicenseApplicationSerializer(
                all_qs.filter(current_stage__name__in=stage_sets['approved']), many=True
            ).data,
            "rejected": LicenseApplicationSerializer(
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
            "pending": LicenseApplicationSerializer(
                all_qs.filter(current_stage__name__in=(role_stage_names | role_objection_stages)), many=True
            ).data,
            "approved": LicenseApplicationSerializer(
                all_qs.filter(current_stage__name__in=forward_stages), many=True
            ).data,
            "rejected": LicenseApplicationSerializer(
                all_qs.filter(current_stage__name__in=role_rejected_stages), many=True
            ).data
        })

    return Response({"detail": "Invalid role"}, status=status.HTTP_400_BAD_REQUEST)
