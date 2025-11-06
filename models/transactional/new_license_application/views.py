from django.shortcuts import get_object_or_404
from django.db import transaction
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.response import Response
from rest_framework import status
from auth.roles.permissions import HasAppPermission
from auth.workflow.permissions import HasStagePermission
from auth.workflow.services import WorkflowService
from .models import NewLicenseApplication, Transaction, Objection
from .serializers import NewLicenseApplicationSerializer, ObjectionSerializer, ResolveObjectionSerializer
from auth.workflow.models import Workflow, WorkflowStage, StagePermission, WorkflowTransition
from django.core.exceptions import ValidationError, PermissionDenied
from django.utils import timezone


@api_view(['POST'])
@permission_classes([HasAppPermission('new_license_application', 'create')])
@parser_classes([MultiPartParser, FormParser])
def create_new_license_application(request):
    serializer = NewLicenseApplicationSerializer(data=request.data)
    if serializer.is_valid():
        with transaction.atomic():
            workflow = get_object_or_404(Workflow, name="License Approval")
            initial_stage = workflow.stages.filter(name="level_1").first()
            if not initial_stage:
                return Response({"detail": "Initial stage not found."}, status=status.HTTP_400_BAD_REQUEST)

            application = serializer.save(
                workflow=workflow,
                current_stage=initial_stage
            )

            # Assign role for the first stage of the workflow
            forwarded_to_role = None
            sp_qs = StagePermission.objects.filter(stage=initial_stage, can_process=True)
            if sp_qs.exists():
                forwarded_to_role = sp_qs.first().role
            if not forwarded_to_role:
                raise ValidationError("No role found for next stage.")

            # Log transaction
            Transaction.objects.create(
                license_application=application,
                performed_by=request.user,
                forwarded_by=request.user,
                forwarded_to=forwarded_to_role,
                stage=initial_stage,
                remarks="Application Submitted"
            )

            #Return the updated application details
            updated_application = NewLicenseApplication.objects.get(pk=application.pk)
            updated_serializer = NewLicenseApplicationSerializer(updated_application)
            return Response(updated_serializer, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@permission_classes([HasAppPermission('license_application', 'view'), HasStagePermission])
@api_view(['GET'])
def list_license_applications(request):
    role = request.user.role.name if request.user.role else None

    if role in ["single_window","site_admin"]:
        applications = NewLicenseApplication.objects.all()
    elif role == "licensee":
        applications = NewLicenseApplication.objects.filter(
            current_stage__name__in=[ "level_1", "awaiting_payment", "level_1_objection", "level_2_objection", "level_3_objection", "level_4_objection", "level_5_objection", "approved"]
        )
    else:
        applications = NewLicenseApplication.objects.filter(
            current_stage__stagepermission__role=request.user.role,
            current_stage__stagepermission__can_process=True
        ).distinct()

    serializer = NewLicenseApplicationSerializer(applications, many=True)
    return Response(serializer.data)

# License Application Detail
@permission_classes([HasAppPermission('license_application', 'view'), HasStagePermission])
@api_view(['GET'])
def license_application_detail(request, pk):
    application = get_object_or_404(NewLicenseApplication, pk=pk)
    serializer = NewLicenseApplicationSerializer(application)
    return Response(serializer.data)

# Advnace Application
@permission_classes([HasAppPermission('license_application', 'update'), HasStagePermission])
@api_view(['POST'])
def advance_license_application(request, application_id, stage_id):
    print(request.data)
   
    # Fetch the application and target stage
    application = get_object_or_404(NewLicenseApplication, application_id=application_id)
    try:
        target_stage = WorkflowStage.objects.get(id=stage_id, workflow=application.workflow)
    except WorkflowStage.DoesNotExist:
        return Response({"detail": f"Stage ID {stage_id} not found in workflow {application.workflow.name}."}, status=status.HTTP_404_NOT_FOUND)
    
    # Extract context_data from request body (e.g., for fee setting, objections, or revert)
    context_data = request.data.get("context",{})
    remarks = request.data.get('remarks', '')

    try:
        with transaction.atomic():
            #Advance the stage using WorkflowService
            WorkflowService.advance_stage(
                application=application,
                user=request.user,
                target_stage=target_stage,
                context_data=context_data,
                remarks = remarks
                )
            
            #Return the updated application details
            updated_application = NewLicenseApplication.objects.get(pk=application.pk)
            serializer = NewLicenseApplicationSerializer(updated_application)
            return Response(serializer.data, status=status.HTTP_200_OK)
        
    except ValidationError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
    except PermissionDenied as e:
            return Response({"detail": str(e)}, status=status.HTTP_403_FORBIDDEN            )
    except Exception as e:
            return Response({"detail": f"Error advancing stage: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
# Raise Objection
@permission_classes([HasAppPermission('license_application', 'update'), HasStagePermission])
@api_view(['POST'])
@parser_classes([JSONParser])
def raise_objection(request, application_id):
    application = get_object_or_404(NewLicenseApplication, application_id=application_id)
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
            updated_application = NewLicenseApplication.objects.get(pk=application.pk)
            serializer = NewLicenseApplicationSerializer(updated_application)
            return Response(serializer.data, status=status.HTTP_200_OK)
        
    except ValidationError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
    except PermissionDenied as e:
            return Response({"detail": str(e)}, status=status.HTTP_403_FORBIDDEN)
    except Exception as e:
            return Response({"detail": f"Error raising objection: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

# Get Objections
@permission_classes([HasAppPermission('license_application', 'view'), HasStagePermission])
@api_view(['GET'])
def get_objections(request, application_id):
    application = get_object_or_404(NewLicenseApplication, pk=application_id)
    objections = Objection.objects.filter(application=application).order_by('-raised_on')
    serializer = ObjectionSerializer(objections, many=True)
    return Response(serializer.data)

# Resolve Objections
@permission_classes([HasAppPermission('license_application', 'update'), HasStagePermission])
@api_view(['POST'])
@parser_classes([JSONParser])
# @transaction.atomic
def resolve_objections(request, application_id):
    application = get_object_or_404(NewLicenseApplication, application_id=application_id)
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
            updated_application = NewLicenseApplication.objects.get(pk=application.pk)
            serializer = NewLicenseApplicationSerializer(updated_application)
            return Response(serializer.data, status=status.HTTP_200_OK)
        
    except ValidationError as e:
        return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
    except PermissionDenied as e:
        return Response({'detail': str(e)}, status=status.HTTP_403_FORBIDDEN)
    except Exception as e:
        return Response({'detail': f"Error resolving objection: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

# Pay License Fee  
@permission_classes([HasAppPermission('license_application', 'view')])
@api_view(['POST'])
def pay_license_fee(request, application_id):
    application = get_object_or_404(NewLicenseApplication, application_id=application_id)

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
        'application': NewLicenseApplicationSerializer(application).data
    })

# Print License View
@permission_classes([HasAppPermission('license_application', 'update')])
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
@permission_classes([HasAppPermission('license_application', 'view'), HasStagePermission])
@api_view(['GET'])
def dashboard_counts(request):
    role = request.user.role.name if request.user.role else None
    counts = {}

    if role in ['level_1', 'level_2', 'level_3', 'level_4', 'level_5']:
        stage = WorkflowStage.objects.get(name=role, workflow__name="License Approval")
        counts = {
            "pending": NewLicenseApplication.objects.filter(current_stage=stage).count(),
            "approved": NewLicenseApplication.objects.filter(
                current_stage__name__in=[
                    f"level_{int(role.split('_')[1]) + 1}", "awaiting_payment", "approved"
                ]
            ).count(),
            "rejected": NewLicenseApplication.objects.filter(
                current_stage__name=f"rejected_by_{role}"
            ).count() if WorkflowStage.objects.filter(name=f"rejected_by_{role}").exists() else 0,
        }

    elif role == 'licensee':
        counts = {
            "applied": NewLicenseApplication.objects.filter(
                current_stage__name__in=['level_1', 'level_2', 'level_3', 'level_4', 'level_5']).count(),
            "pending": NewLicenseApplication.objects.filter(
                current_stage__name__in=[
                    'level_1_objection',
                    'level_2_objection',
                    'level_3_objection',
                    'level_4_objection',
                    'level_5_objection',
                    'awaiting_payment'
                ]
            ).count(),
            "approved": NewLicenseApplication.objects.filter(
                current_stage__name='approved', is_approved=True
            ).count(),
            "rejected": NewLicenseApplication.objects.filter(
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
            "applied": NewLicenseApplication.objects.filter(current_stage__name__in=[
                'applicant_applied', 'level_1_objection',
                'level_2_objection', 'level_3_objection',
                'level_4_objection', 'level_5_objection',
                'awaiting_payment'
                ]).count(),
            "pending": NewLicenseApplication.objects.filter(current_stage__name__in=[
                'level_1','level_2','level_3','level_4','level_5',
                ]).count(),
            "approved": NewLicenseApplication.objects.filter(
                current_stage__name='approved', is_approved=True
            ).count(),
            "rejected": NewLicenseApplication.objects.filter(
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

# Application Grouping
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
            queryset = NewLicenseApplication.objects.filter(current_stage__name__in=stages)
            if key == 'rejected':
                queryset = queryset.filter(is_approved=False)
            result[key] = NewLicenseApplicationSerializer(queryset, many=True).data
        return Response(result)

    elif role == 'licensee':
        result = {
            "applied": NewLicenseApplicationSerializer(
                NewLicenseApplication.objects.filter(current_stage__name__in=[
                    'level_1', 'level_2', 'level_3', 'level_4', 'level_5'
                    ]),
                many=True
            ).data,
            "pending": NewLicenseApplicationSerializer(
                NewLicenseApplication.objects.filter(current_stage__name__in=[
                    'level_1_objection',
                    'level_2_objection',
                    'level_3_objection',
                    'level_4_objection',
                    'level_5_objection',
                    'awaiting_payment'
                ]),
                many=True
            ).data,
            "approved": NewLicenseApplicationSerializer(
                NewLicenseApplication.objects.filter(current_stage__name='approved'),
                many=True
            ).data,
            "rejected": NewLicenseApplicationSerializer(
                NewLicenseApplication.objects.filter(current_stage__name__in=[
                    'rejected_by_level_1', 'rejected_by_level_2',
                    'rejected_by_level_3', 'rejected_by_level_4',
                    'rejected_by_level_5', 'rejected'
                ]),
                many=True
            ).data
        }
        return Response(result)

    return Response({"detail": "Invalid role"}, status=status.HTTP_400_BAD_REQUEST)

# Get Next Stages
@permission_classes([HasAppPermission('license_application', 'view'), HasStagePermission])
@api_view(['GET'])
def get_next_stages(request, application_id):
    application = get_object_or_404(NewLicenseApplication, application_id=application_id)
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