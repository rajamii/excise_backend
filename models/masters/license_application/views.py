from django.shortcuts import get_object_or_404
from django.db import transaction
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.parsers import JSONParser, MultiPartParser, FormParser
from rest_framework.response import Response
from django.core.exceptions import ValidationError
from auth.roles.permissions import HasAppPermission
from .models import LicenseApplication, SiteEnquiryReport, LocationFee, Objection
from .serializers import LicenseApplicationSerializer, SiteEnquiryReportSerializer, LocationFeeSerializer, ObjectionSerializer, ResolveObjectionSerializer
from .services.workflow import advance_application
from .models import LicenseApplicationTransaction
from models.masters.core.models import LicenseCategory
from django.utils import timezone
from rest_framework import status
from auth.roles.models import Role

#################################################
#           License Application                 #
#################################################

@permission_classes([HasAppPermission('license_application', 'create')])
@api_view(['POST'])
@parser_classes([MultiPartParser, FormParser])
def create_license_application(request):
    serializer = LicenseApplicationSerializer(data=request.data)
    if serializer.is_valid():
        with transaction.atomic():
            application = serializer.save(current_stage='level_1')

            # Assign role for the first stage of the workflow
            forwarded_to_role = Role.objects.filter(name='level_1').first()
            if not forwarded_to_role:
                raise ValidationError("No role found for next stage: level_1")

            # Log the creation of the application in transaction table
            LicenseApplicationTransaction.objects.create(
                license_application=application,
                performed_by=request.user,
                forwarded_by=request.user,
                forwarded_to=forwarded_to_role,
                stage='level_1',
                remarks='License Applied'
            )
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@permission_classes([HasAppPermission('license_application', 'view')])
@api_view(['GET'])
def list_license_applications(request):
    applications = LicenseApplication.objects.all()
    serializer = LicenseApplicationSerializer(applications, many=True)
    return Response(serializer.data)


@permission_classes([HasAppPermission('license_application', 'view')])
@api_view(['GET'])
def license_application_detail(request, pk):
    application = get_object_or_404(LicenseApplication, pk=pk)
    serializer = LicenseApplicationSerializer(application)
    return Response(serializer.data)


@permission_classes([HasAppPermission('license_application', 'delete')])
@api_view(['DELETE'])
def delete_license_application(request, application_id):
    application = get_object_or_404(LicenseApplication, application_id=application_id)

    if application.current_stage != 'level_1':
        return Response(
            {'detail': 'Deletion not allowed. Application has already been forwarded.'},
            status=status.HTTP_403_FORBIDDEN
        )

    application.delete()
    return Response({'detail': 'Application deleted successfully.'}, status=status.HTTP_204_NO_CONTENT)


@permission_classes([HasAppPermission('license_application', 'update')])
@api_view(['POST'])
def advance_license_application(request, application_id):
    print(request.data)
    application = get_object_or_404(LicenseApplication, pk=application_id) 
    user = request.user

    # Extract required fields from request
    remarks = request.data.get("remarks", "")
    fee_amount = request.data.get("fee_amount")
    new_license_category_id = request.data.get("new_license_category")
    action = request.data.get("action")
    objections = request.data.get("objections", [])

    # Validate license category change if requested
    new_license_category = None
    if new_license_category_id:
        try:
            new_license_category = LicenseCategory.objects.get(pk=new_license_category_id)
        except LicenseCategory.DoesNotExist:
            return Response({"detail": "Invalid license category ID."}, status=status.HTTP_400_BAD_REQUEST)

    try:
        if action == 'raise_objection':
            # Objection format must include field and remarks keys
            if not isinstance(objections, list) or not all('field' in obj and 'remarks' in obj for obj in objections):
                return Response({"detail": "Invalid objections format."}, status=status.HTTP_400_BAD_REQUEST)
            
        # Perform workflow action
        advance_application(
            application,
            user,
            remarks=remarks,
            action=action,
            new_license_category=new_license_category,
            fee_amount=fee_amount,
            objections=objections
        )

        return Response({"detail": "Application advanced successfully."}, status=status.HTTP_200_OK)

    except ValidationError as ve:
        return Response({"detail": str(ve)}, status=status.HTTP_400_BAD_REQUEST)


@permission_classes([HasAppPermission('license_application', 'update')])
@api_view(['GET', 'POST'])
@parser_classes([MultiPartParser, FormParser])
def level2_site_enquiry(request, application_id):
    application = get_object_or_404(LicenseApplication, pk=application_id)
    try:
        report = application.site_enquiry_report
    except SiteEnquiryReport.DoesNotExist:
        report = None

    if request.method == 'POST':
        serializer = SiteEnquiryReportSerializer(data=request.data, instance=report)
        if serializer.is_valid():
            serializer.save(application=application)
            return Response(serializer.data, status=200)
        else:  
            return Response(serializer.errors, status=400)

    if report:
        serializer = SiteEnquiryReportSerializer(report)
        return Response(serializer.data)
    else:
        return Response({"detail": "No report found."}, status=404)
    
    
@permission_classes([HasAppPermission('license_application', 'view')])
@api_view(['GET'])
def site_enquiry_detail(request, application_id):
    application = get_object_or_404(SiteEnquiryReport, application_id=application_id)
    serializer = SiteEnquiryReportSerializer(application)
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

@permission_classes([HasAppPermission('license_application', 'view')])
@api_view(['POST'])
def pay_license_fee(request, application_id):
    try:
        application = LicenseApplication.objects.get(application_id=application_id)
    except LicenseApplication.DoesNotExist:
        raise ValidationError("Invalid application ID.")

    # Enforce payment flow strictly at correct stage
    if application.current_stage != 'awaiting_payment':
        raise ValidationError("Payment not allowed at current stage.")

    if application.is_license_fee_paid:
        raise ValidationError("Payment already completed.")

    # Mark fee as paid and move to next stage
    application.is_license_fee_paid = True
    application.current_stage = 'level_3'
    application.save()

    # Get next role responsible
    try:
        forwarded_to_role = Role.objects.get(name='level_3')
    except Role.DoesNotExist:
        raise ValidationError("Next stage role (level_3) not found.")

    # Log the fee payment in the transaction table
    LicenseApplicationTransaction.objects.create(
        license_application=application,
        stage=application.current_stage,
        performed_by=request.user,
        forwarded_by=request.user,
        forwarded_to=forwarded_to_role,
        remarks='License fee paid by applicant.',
    )

    return Response({
        'message': 'License fee payment recorded successfully.',
        'application': LicenseApplicationSerializer(application).data
    })

@permission_classes([HasAppPermission('license_application', 'view')])
@api_view(['GET'])
def get_objections(request, application_id):
    objections = Objection.objects.filter(application_id=application_id).order_by('-raised_on')
    serializer = ObjectionSerializer(objections, many=True)
    return Response(serializer.data)

@permission_classes([HasAppPermission('license_application', 'update')])
@api_view(['POST'])
@parser_classes([MultiPartParser, FormParser])
@transaction.atomic
def resolve_objections(request, application_id):
    application = get_object_or_404(LicenseApplication, application_id=application_id)

    serializer = ResolveObjectionSerializer(application, data=request.data, partial=True)
    serializer.is_valid(raise_exception=True)
    serializer.save()

    # Validate objection stage
    if not application.current_stage.endswith('_objection'):
        return Response(
            {"error": "Current stage is not objection-related."},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Restore original stage
    original_stage = application.current_stage.replace('_objection', '')
    application.current_stage = original_stage
    application.save()

    # Resolve objections
    Objection.objects.filter(application=application, is_resolved=False).update(
        is_resolved=True, resolved_on=timezone.now()
    )

    # Log transaction
    last_objection = Objection.objects.filter(application=application).order_by('-id').first()
    raised_by = last_objection.raised_by if last_objection else None

    LicenseApplicationTransaction.objects.create(
        license_application=application,
        performed_by=request.user,
        forwarded_by=request.user,
        forwarded_to=raised_by.role if raised_by else None,
        stage=original_stage,
        remarks="Objection resolved and application moved back to review stage."
    )

    return Response({"message": "Objections resolved and application reverted to previous stage."})


@permission_classes([HasAppPermission('license_application', 'view')])
@api_view(['GET'])
@parser_classes([JSONParser])
def dashboard_counts(request):
    role = request.user.role.name if request.user.role else None

    level_map = {
        'level_1': {
            "pending": ['level_1', 'level_1_objection'],
            "approved": 'level_2',
            "rejected": 'rejected_by_level_1',
        },
        'level_2': {
            "pending": ['level_2', 'level_2_objection'],
            "approved": 'awaiting_payment',
            "rejected": 'rejected_by_level_2',
        },
        'level_3': {
            "pending": ['level_3', 'level_3_objection'],
            "approved": 'level_4',
            "rejected": 'rejected_by_level_3',
        },
        'level_4': {
            "pending": ['level_4', 'level_4_objection'],
            "approved": 'level_5',
            "rejected": 'rejected_by_level_4',
        },
        'level_5': {
            "pending": ['level_5', 'level_5_objection'],
            "approved": 'approved',
            "rejected": 'rejected_by_level_5',
        }
    }

    if role in level_map:
        config = level_map[role]
        counts = {}

        for key, stage in config.items():
            if isinstance(stage, list):
                counts[key] = LicenseApplication.objects.filter(current_stage__in=stage).count()
            else:
                counts[key] = LicenseApplication.objects.filter(current_stage=stage).count()

        return Response(counts)

    elif role == 'licensee':
        counts = {
            "applied": LicenseApplication.objects.filter(current_stage='level_1').count(),
            "pending": LicenseApplication.objects.filter(current_stage__in=[
                'level_1_objection',
                'level_2', 'level_2_objection',
                'level_3', 'level_3_objection',
                'level_4', 'level_4_objection',
                'level_5', 'level_5_objection',
                'awaiting_payment'
            ]).count(),
            "approved": LicenseApplication.objects.filter(
                current_stage='approved', is_approved=True
            ).count(),
            "rejected": LicenseApplication.objects.filter(
                current_stage__in=
                [
                    'rejected_by_level_1', 
                    'rejected_by_level_2',
                    'rejected_by_level_3',
                    'rejected_by_level_4',
                    'rejected_by_level_5',
                    'rejected',
                ]
            ).count()
        }
        return Response(counts)

    elif role == 'site_admin':
        counts = {
            "applied": LicenseApplication.objects.filter(current_stage='level_1').count(),
            "pending": LicenseApplication.objects.filter(current_stage__in=[
                'level_1_objection',
                'level_2', 'level_2_objection',
                'level_3', 'level_3_objection',
                'level_4', 'level_4_objection',
                'level_5', 'level_5_objection',
            ]).count(),
            "approved": LicenseApplication.objects.filter(
                current_stage='approved', is_approved=True
            ).count(),
            "rejected": LicenseApplication.objects.filter(
                current_stage__in=[
                    'rejected_by_level_1', 
                    'rejected_by_level_2',
                    'rejected_by_level_3',
                    'rejected_by_level_4',
                    'rejected_by_level_5',
                    'rejected',
                ]
            ).count()
        }
        return Response(counts)

    return Response({"detail": "Invalid role"}, status=status.HTTP_400_BAD_REQUEST)


@permission_classes([HasAppPermission('license_application', 'view')])
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
            "approved": ['awaiting_payment'],
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
            queryset = LicenseApplication.objects.filter(current_stage__in=stages)

            if key == 'rejected':
                queryset = queryset.filter(is_approved=False)

            result[key] = LicenseApplicationSerializer(queryset, many=True).data

        return Response(result)

    elif role == 'licensee':
        result = {
            "applied": LicenseApplicationSerializer(
                LicenseApplication.objects.filter(current_stage='level_1'),
                many=True
            ).data,
            "pending": LicenseApplicationSerializer(
                LicenseApplication.objects.filter(current_stage__in=[
                    'level_1_objection',
                    'level_2', 'level_2_objection',
                    'level_3', 'level_3_objection',
                    'level_4', 'level_4_objection',
                    'level_5', 'level_5_objection',
                    'awaiting_payment'
                ]),
                many=True
            ).data,
            "approved": LicenseApplicationSerializer(
                LicenseApplication.objects.filter(current_stage='approved'),
                many=True
            ).data,
            "rejected": LicenseApplicationSerializer(
                LicenseApplication.objects.filter(current_stage__in=[
                    'rejected_by_level_1', 'rejected_by_level_2',
                    'rejected_by_level_3', 'rejected_by_level_4',
                    'rejected_by_level_5', 'rejected'
                ]),
                many=True
            ).data
        }
        return Response(result)

    return Response({"detail": "Invalid role"}, status=status.HTTP_400_BAD_REQUEST)
