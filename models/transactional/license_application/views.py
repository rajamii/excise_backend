from django.shortcuts import get_object_or_404
from django.db import transaction
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.parsers import JSONParser, MultiPartParser, FormParser
from rest_framework.response import Response
from django.core.exceptions import ValidationError, PermissionDenied
from auth.roles.permissions import HasAppPermission
from .models import LicenseApplication
from models.masters.core.models import LocationFee
from .serializers import LicenseApplicationSerializer, LocationFeeSerializer, ResolveObjectionSerializer
from auth.workflow.models import Objection
from auth.workflow.serializers import WorkflowObjectionSerializer
from django.utils import timezone
from rest_framework import status
from auth.workflow.models import Workflow, StagePermission, WorkflowStage, WorkflowTransition
from auth.workflow.permissions import HasStagePermission
from auth.workflow.services import WorkflowService

#################################################
#           License Application                 #
#################################################

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


@permission_classes([HasAppPermission('license_application', 'view'), HasStagePermission])
@api_view(['GET'])
def list_license_applications(request):
    role = request.user.role.name if request.user.role else None

    if role in ["single_window","site_admin"]:
        applications = LicenseApplication.objects.all()
    elif role == "licensee":
        applications = LicenseApplication.objects.filter(
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


@permission_classes([HasAppPermission('license_application', 'delete'), HasStagePermission])
@api_view(['DELETE'])
def delete_license_application(request, application_id):
    application = get_object_or_404(LicenseApplication, application_id=application_id)

    if application.current_stage.name != 'level_1':
        return Response(
            {'detail': 'Deletion not allowed. Application has already been forwarded.'},
            status=status.HTTP_403_FORBIDDEN
        )

    application.delete()
    return Response({'detail': 'Application deleted successfully.'}, status=status.HTTP_204_NO_CONTENT)


@permission_classes([HasAppPermission('license_application', 'update'), HasStagePermission])
@api_view(['POST'])
def advance_license_application(request, application_id, stage_id):
    print(request.data)
    
    # Fetch the application and target stage
    application = get_object_or_404(LicenseApplication, application_id=application_id)
    try:
       target_stage = get_object_or_404(WorkflowStage, id=stage_id)
    except WorkflowStage.DoesNotExist:
        return Response({"detail": f"Stage ID {stage_id} not found in workflow {application.workflow.name}."}, status=status.HTTP_404_NOT_FOUND)
    
    # Extract context_data from request body (e.g., for fee setting, objections, or revert)
    context = request.data.get("context",{})
    # remarks = request.data.get('remarks', '')

    try:
        with transaction.atomic():
            #Advance the stage using WorkflowService
            WorkflowService.advance_stage(
                application=application,
                user=request.user,
                target_stage=target_stage,
                context=context,
                # remarks = remarks
                )
            
            #Return the updated application details
            updated_application = LicenseApplication.objects.get(pk=application.pk)
            serializer = LicenseApplicationSerializer(updated_application)
            return Response(serializer.data, status=status.HTTP_200_OK)
        
    except ValidationError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
    except PermissionDenied as e:
            return Response({"detail": str(e)}, status=status.HTTP_403_FORBIDDEN)
    except Exception as e:
            return Response({"detail": f"Error advancing stage: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@permission_classes([HasAppPermission('license_application', 'update'), HasStagePermission])
@api_view(['POST'])
@parser_classes([JSONParser])
def raise_objection(request, application_id):
    application = get_object_or_404(LicenseApplication, application_id=application_id)
    objections = request.data.get('objections', [])
    remarks = request.data.get('remarks', '')

    #Determine objection stage
    current_stage_name=application.current_stage.name
    if not current_stage_name.startswith('level_'):
        return Response({'detail': 'Objections can only be raised from level_X stages'},
                        status=status.HTTP_400_BAD_REQUEST)

    objection_stage_name = f"{current_stage_name}_objection"
    target_stage = get_object_or_404(WorkflowStage, workflow=application.workflow, name=objection_stage_name)

    try:
        with transaction.atomic():
            WorkflowService.raise_objection(
                application=application,
                user=request.user,
                target_stage=target_stage,
                objections=objections,
                remarks=remarks
            )

            #Return the updated application details
            updated_application = LicenseApplication.objects.get(pk=application.pk)
            serializer = LicenseApplicationSerializer(updated_application)
            return Response(serializer.data, status=status.HTTP_200_OK)
        
    except ValidationError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
    except PermissionDenied as e:
            return Response({"detail": str(e)}, status=status.HTTP_403_FORBIDDEN)
    except Exception as e:
            return Response({"detail": f"Error raising objection: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@permission_classes([HasAppPermission('license_application', 'view'), HasStagePermission])
@api_view(['GET'])
def get_objections(request, application_id):
    application = get_object_or_404(LicenseApplication, pk=application_id)
    objections = application.objections.all().order_by('-raised_on')
    serializer = WorkflowObjectionSerializer(objections, many=True)
    return Response(serializer.data)

@permission_classes([HasAppPermission('license_application', 'update'), HasStagePermission])
@api_view(['POST'])
@parser_classes([JSONParser])
# @transaction.atomic
def resolve_objections(request, application_id):
    application = get_object_or_404(LicenseApplication, application_id=application_id)
    if request.user.role.name != "licensee":
        return Response ({"detail": "Only licensee can resolve objections."}, status= status.HTTP_403_FORBIDDEN)
    
    # Validate current stage is an objection stage
    current_stage_name = application.current_stage.name
    if not current_stage_name.endswith('_objection'):
        return Response({"detail": "Application is not in an objection stage."}, status=status.HTTP_400_BAD_REQUEST)
    
    # Determine target stage
    target_stage_name = current_stage_name.replace('_objection', '')
    target_stage = get_object_or_404(WorkflowStage, workflow=application.workflow, name=target_stage_name)

    # Validate and update application fields
    serializer = ResolveObjectionSerializer(application, data=request.data, partial=True)
    if not serializer.is_valid():
        return Response({'detail': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        with transaction.atomic():
            serializer.save()

            # Create Objection record
            Objection.objects.filter(application=application, is_resolved=False).update(
                is_resolved=True,
                resolved_on=timezone.now(),
            )

            #Advance to original stage
            WorkflowService.resolve_objection(
                application=application,
                user=request.user,
                target_stage=target_stage,
                context_data={"objections_resolved": True, "remarks": request.data.get("remarks", "Objections resolved.")}
            )

            #Return updated application
            updated_application = LicenseApplication.objects.get(pk=application.pk)
            serializer = LicenseApplicationSerializer(updated_application)
            return Response(serializer.data, status=status.HTTP_200_OK)
        
    except ValidationError as e:
        return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
    except PermissionDenied as e:
        return Response({'detail': str(e)}, status=status.HTTP_403_FORBIDDEN)
    except Exception as e:
        return Response({'detail': f"Error resolving objection: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


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
    application = get_object_or_404(LicenseApplication, application_id=application_id)

    if application.current_stage.name != 'awaiting_payment':
        return Response({"detail": "Payment not allowed at current stage."}, status=400)

    if application.is_license_fee_paid:
        return Response({"detail": "Payment already completed."}, status=400)

    application.is_license_fee_paid = True
    application.save(update_fields=['is_license_fee_paid'])

    target_stage = WorkflowStage.objects.filter(
        workflow=application.workflow, name='level_3'
    ).first()
    if not target_stage:
        return Response({"detail": "Target stage level_3 not found."}, status=400)

    try:
        WorkflowService.advance_stage(
            application=application,
            user=request.user,
            target_stage=target_stage,
            context_data={"payment_done": True},
            skip_permission_check=False
        )
    except ValidationError as e:
        return Response({"detail": str(e)}, status=400)

    return Response({
        'message': 'License fee payment recorded successfully.',
        'application': LicenseApplicationSerializer(application).data
    })


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
        counts = {
            "applied": LicenseApplication.objects.filter(
                current_stage__name__in=['level_1', 'level_2', 'level_3', 'level_4', 'level_5']).count(),
            "pending": LicenseApplication.objects.filter(
                current_stage__name__in=[
                    'level_1_objection',
                    'level_2_objection',
                    'level_3_objection',
                    'level_4_objection',
                    'level_5_objection',
                    'awaiting_payment'
                ]
            ).count(),
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
        result = {
            "applied": LicenseApplicationSerializer(
                LicenseApplication.objects.filter(current_stage__name__in=[
                    'level_1', 'level_2', 'level_3', 'level_4', 'level_5'
                    ]),
                many=True
            ).data,
            "pending": LicenseApplicationSerializer(
                LicenseApplication.objects.filter(current_stage__name__in=[
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
                LicenseApplication.objects.filter(current_stage__name='approved'),
                many=True
            ).data,
            "rejected": LicenseApplicationSerializer(
                LicenseApplication.objects.filter(current_stage__name__in=[
                    'rejected_by_level_1', 'rejected_by_level_2',
                    'rejected_by_level_3', 'rejected_by_level_4',
                    'rejected_by_level_5', 'rejected'
                ]),
                many=True
            ).data
        }
        return Response(result)

    return Response({"detail": "Invalid role"}, status=status.HTTP_400_BAD_REQUEST)

@permission_classes([HasAppPermission('license_application', 'view'), HasStagePermission])
@api_view(['GET'])
def get_next_stages(request, application_id):
    application = get_object_or_404(LicenseApplication, application_id=application_id)
    current_stage = application.current_stage

    # Get all transitions from current stage within the same workflow
    transitions = WorkflowTransition.objects.filter(workflow=application.workflow, from_stage=current_stage)

    allowed_stages = [t.to_stage for t in transitions]

    # Serialize stage info
    data = [{
        'id': stage.id,
        'name': stage.name,
        'description': stage.description
    } for stage in allowed_stages]

    return Response(data)
