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
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
import secrets
from models.transactional.wallet.wallet_service import debit_wallet_balance
from models.transactional.wallet.wallet_initializer import _resolve_hoa_code
from models.transactional.payment_gateway.models import MasterPaymentModule



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
        payment_stages = set(stage_sets['payment'])
        pending_stages = set(stage_sets['all']) - applied_stages - approved_stages - rejected_stages - objection_stages - payment_stages

        return Response({
            # Licensee UX: application is considered "Pending" until application-fee payment succeeds.
            "applied": base_qs.filter(current_stage__name__in=applied_stages).count(),
            "pending": base_qs.filter(current_stage__name__in=pending_stages).count(),
            "objection": base_qs.filter(current_stage__name__in=objection_stages).count(),
            "approved": base_qs.filter(current_stage__name__in=approved_stages).count(),
            "rejected": base_qs.filter(current_stage__name__in=rejected_stages).count(),
            "awaiting_payment": base_qs.filter(current_stage__name__in=payment_stages).count(),
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
        payment_stages = set(stage_sets['payment'])
        pending_stages = set(stage_sets['all']) - applied_stages - approved_stages - rejected_stages - objection_stages - payment_stages

        return Response({
            "applied": CompanyRegistrationSerializer(
                base_qs.filter(current_stage__name__in=applied_stages), many=True
            ).data,
            "pending": CompanyRegistrationSerializer(
                base_qs.filter(current_stage__name__in=pending_stages), many=True
            ).data,
            "objection": CompanyRegistrationSerializer(
                base_qs.filter(current_stage__name__in=objection_stages), many=True
            ).data,
            "approved": CompanyRegistrationSerializer(
                base_qs.filter(current_stage__name__in=approved_stages), many=True
            ).data,
            "rejected": CompanyRegistrationSerializer(
                base_qs.filter(current_stage__name__in=rejected_stages), many=True
            ).data,
            "awaiting_payment": CompanyRegistrationSerializer(
                base_qs.filter(current_stage__name__in=payment_stages), many=True
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


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def pay_company_registration_fee(request, application_id):
    """
    Wallet debit for Company Registration fee (module_code=009).
    On success, advance workflow from Awaiting Payment -> Approved.
    """
    from decimal import Decimal
    application = get_object_or_404(CompanyRegistration, application_id=application_id)
    
    # Verify user is licensee
    role_name = request.user.role.name if request.user.role else None
    if _normalize_role(role_name) != 'licensee':
        return Response({"detail": "Only licensees can pay the registration fee."}, status=status.HTTP_403_FORBIDDEN)
        
    if application.applicant != request.user:
        return Response({"detail": "Not found or not authorized."}, status=status.HTTP_404_NOT_FOUND)

    # Only allow payment once the application is in Awaiting Payment.
    current_stage_name = application.current_stage.name if application.current_stage else ""
    if current_stage_name != "Awaiting Payment":
        return Response(
            {"detail": f"Application is in '{current_stage_name}', not Awaiting Payment stage."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Get the fee amount dynamically from masters_fixedfee table (admin-updatable)
    try:
        from django.apps import apps
        FixedFee = apps.get_model('core', 'MasterFixedFee')
        fee_obj = FixedFee.objects.filter(fee_code='COMP_REG', is_active=True).first()
        amount = fee_obj.amount if fee_obj else Decimal('5000.00')
    except Exception:
        amount = Decimal('5000.00')

    # Resolve wallet licensee id (username) and HOA
    wallet_licensee_id = str(getattr(request.user, "username", "") or "").strip()
    license_fee_hoa = _resolve_hoa_code(module_type="other", wallet_type="license_fee")

    txn_id = secrets.token_hex(12).upper()
    try:
        debit_wallet_balance(
            transaction_id=txn_id,
            licensee_id=wallet_licensee_id,
            wallet_type="license_fee",
            head_of_account=license_fee_hoa,
            amount=amount,
            user_id=wallet_licensee_id,
            remarks=f"Company Registration fee paid for {application.application_id}",
            reference_no=application.application_id,
        )
    except Exception as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    # Advance to Approved stage
    try:
        with transaction.atomic():
            application.payment_amount = amount
            application.payment_remarks = f"Paid via license wallet. Trans ID: {txn_id}"
            application.is_approved = True
            application.save()

            approved_stage = application.workflow.stages.filter(name__iexact="approved").order_by("id").first()
            if approved_stage:
                WorkflowService.advance_stage(
                    application=application,
                    user=request.user,
                    target_stage=approved_stage,
                    context={"action": "PAY"},
                    remarks="Company Registration fee paid via wallet",
                )
                application.refresh_from_db()
    except Exception as exc:
        return Response({"detail": f"Payment succeeded but workflow advance failed: {str(exc)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    return Response({"success": True, "transaction_id": txn_id})


