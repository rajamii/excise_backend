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
from auth.workflow.permissions import HasStagePermission
from auth.workflow.services import WorkflowService

def _create_application(request, workflow_name: str, serializer_cls):
    
    serializer = serializer_cls(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    with transaction.atomic():
        workflow = get_object_or_404(Workflow, name=workflow_name)
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
    return _create_application(request, "License Approval", LicenseApplicationSerializer)


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

        workflow = get_object_or_404(Workflow, name="License Approval")
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
    role = request.user.role.name if request.user.role else None

    if role in ["single_window","site_admin"]:
        applications = LicenseApplication.objects.all()
    elif role == "licensee":
        applications = LicenseApplication.objects.filter(
            applicant = request.user,
            current_stage__name__in=[ "level_1", "awaiting_payment", "level_1_objection", "level_2_objection", "level_3_objection", "level_4_objection", "level_5_objection", "approved"]
        )
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
    role = request.user.role.name if request.user.role else None
    counts = {}

    if role in ['level_1', 'level_2', 'level_3', 'level_4', 'level_5']:
        stage = WorkflowStage.objects.get(name=role, workflow__name="License Approval")
        counts = {
            "pending": LicenseApplication.objects.filter(current_stage=stage).count(),
            "approved": LicenseApplication.objects.filter(
                current_stage__name__in=[
                    f"level_{int(role.split('_')[1]) + 1}", "awaiting_payment", "approved"
                ]
            ).count(),
            "rejected": LicenseApplication.objects.filter(
                current_stage__name=f"rejected_by_{role}"
            ).count() if WorkflowStage.objects.filter(name=f"rejected_by_{role}").exists() else 0,
        }

    elif role == 'licensee':
        base_qs = LicenseApplication.objects.filter(applicant=request.user)
        counts = {
            "applied": base_qs.filter(
                current_stage__name__in=['level_1', 'level_2', 'level_3', 'level_4', 'level_5']).count(),
            "pending":base_qs.filter(
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
            "applied": LicenseApplication.objects.filter(current_stage__name__in=[
                'applicant_applied', 'level_1_objection',
                'level_2_objection', 'level_3_objection',
                'level_4_objection', 'level_5_objection',
                'awaiting_payment'
                ]).count(),
            "pending": LicenseApplication.objects.filter(current_stage__name__in=[
                'level_1','level_2','level_3','level_4','level_5',
                ]).count(),
            "approved": LicenseApplication.objects.filter(
                current_stage__name='approved', is_approved=True
            ).count(),
            "rejected": LicenseApplication.objects.filter(
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
            queryset = LicenseApplication.objects.filter(current_stage__name__in=stages)
            if key == 'rejected':
                queryset = queryset.filter(is_approved=False)
            result[key] = LicenseApplicationSerializer(queryset, many=True).data
        return Response(result)

    elif role == 'licensee':
        base_qs = LicenseApplication.objects.filter(applicant=request.user)
        result = {
            "applied": LicenseApplicationSerializer(
               base_qs.filter(current_stage__name__in=[
                    'level_1', 'level_2', 'level_3', 'level_4', 'level_5'
                    ]),
                many=True
            ).data,
            "pending": LicenseApplicationSerializer(
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
            "approved": LicenseApplicationSerializer(
                base_qs.filter(current_stage__name='approved'),
                many=True
            ).data,
            "rejected": LicenseApplicationSerializer(
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