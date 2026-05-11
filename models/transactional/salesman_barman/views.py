from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.response import Response
from rest_framework import status
from auth.roles.permissions import HasAppPermission
from auth.workflow.permissions import HasStagePermission
from auth.workflow.models import Workflow, WorkflowStage, WorkflowTransition
from auth.workflow.models import Transaction as WorkflowTransaction
from auth.workflow.constants import WORKFLOW_IDS
from auth.workflow.services import WorkflowService
from models.masters.license.models import License
from .models import SalesmanBarmanModel
from .serializers import SalesmanBarmanSerializer
import re
import secrets

from rest_framework.permissions import IsAuthenticated
from django.core.exceptions import PermissionDenied
from django.contrib.contenttypes.models import ContentType
from models.transactional.payment_gateway.models import MasterPaymentModule
from models.transactional.wallet.wallet_initializer import COMMON_LICENSE_FEE_HOA
from models.transactional.wallet.wallet_service import debit_wallet_balance


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


def _get_in_progress_stage_names(stage_sets: dict):
    # Any non-final processing stage should be treated as in-progress/pending.
    return set(stage_sets['all']) - set(stage_sets['approved']) - set(stage_sets['rejected'])


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


def _build_role_transition_buckets(user, workflow_id: int, stage_sets: dict):
    role = getattr(user, 'role', None)
    if not role:
        return None

    role_stages = WorkflowStage.objects.filter(
        workflow_id=workflow_id,
        stagepermission__role=role,
        stagepermission__can_process=True
    ).distinct()

    role_stage_ids = set(role_stages.values_list('id', flat=True))
    role_stage_names = set(role_stages.values_list('name', flat=True))
    if not role_stage_ids:
        return None

    transitions = WorkflowTransition.objects.filter(
        workflow_id=workflow_id,
        from_stage_id__in=role_stage_ids
    ).select_related('to_stage')

    approved_targets = set()
    rejected_targets = set()
    objection_targets = set()

    for t in transitions:
        to_name = str(t.to_stage.name or '')
        to_name_lower = to_name.lower()
        condition = t.condition or {}
        action = str(condition.get('action') or '').strip().upper()

        if action == 'REJECT' or 'reject' in to_name_lower:
            rejected_targets.add(to_name)
            continue

        if action in {'RAISE_OBJECTION', 'OBJECTION'} or 'objection' in to_name_lower:
            objection_targets.add(to_name)
            continue

        approved_targets.add(to_name)

    pending_names = set(role_stage_names)
    approved_names = set(approved_targets) | set(stage_sets['approved']) | set(stage_sets['payment'])
    rejected_names = set(rejected_targets) | set(stage_sets['rejected'])
    objection_names = set(objection_targets) | set(stage_sets['objection'])

    return {
        'pending': pending_names,
        'approved': approved_names,
        'rejected': rejected_names,
        'objection': objection_names,
    }

def _create_application(request, workflow_id: int, serializer_cls):
    
    serializer = serializer_cls(data=request.data)
    if not serializer.is_valid():
        print("Validation errors:", serializer.errors)
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

        # 3. Generic workflow submission and auto-forward
        WorkflowService.submit_application(
            application=application,
            user=request.user,
            remarks="Application submitted",
        )

        # 4. Return the *fresh* object (includes generic relations)
        fresh = SalesmanBarmanModel.objects.get(pk=application.pk)
        fresh_serializer = serializer_cls(fresh)
        return Response(fresh_serializer.data, status=status.HTTP_201_CREATED)


def _require_licensee_user(request):
    role = _normalize_role(getattr(getattr(request.user, "role", None), "name", None))
    if role != "licensee":
        raise PermissionDenied("Only licensee can pay from wallet.")


def _resolve_sb_license_for_application(application: SalesmanBarmanModel) -> License | None:
    try:
        ct = ContentType.objects.get_for_model(SalesmanBarmanModel)
        return (
            License.objects.filter(
                source_type="salesman_barman",
                source_content_type=ct,
                source_object_id=str(application.pk),
            )
            .order_by("-issue_date", "-license_id")
            .first()
        )
    except Exception:
        return None


def _get_salesman_barman_registration_fee() -> float | None:
    module = MasterPaymentModule.objects.filter(module_code="012").only("license_fee").first()
    if not module:
        return None
    try:
        return float(getattr(module, "license_fee", None))
    except Exception:
        return None


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@parser_classes([JSONParser, FormParser, MultiPartParser])
def pay_registration_fee_wallet(request, application_id):
    """
    Wallet debit for Salesman/Barman Registration fee (module_code=012).
    On success, advance workflow from awaiting_payment -> approved.
    """
    application = get_object_or_404(SalesmanBarmanModel, application_id=application_id)
    _require_licensee_user(request)
    if application.applicant_id != request.user.id:
        return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

    # Only allow payment once the application is routed to awaiting_payment.
    try:
        from models.transactional.salesman_barman.payment_status import get_awaiting_payment_stage

        awaiting_stage = get_awaiting_payment_stage(application)
        if awaiting_stage and application.current_stage_id != awaiting_stage.id:
            return Response(
                {"detail": "Application is not in payment stage."},
                status=status.HTTP_400_BAD_REQUEST,
            )
    except Exception:
        pass

    lic = _resolve_sb_license_for_application(application)
    if not lic:
        return Response({"detail": "License not issued yet."}, status=status.HTTP_400_BAD_REQUEST)

    amount = _get_salesman_barman_registration_fee()
    if amount is None or amount <= 0:
        return Response(
            {"detail": "Registration fee is not configured for Salesman/Barman (module_code=012)."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # The wallet is keyed by the licensee's NLI license ID (the one recharged via BillDesk),
    # not the SB license ID. Resolve the NLI license ID from the linked NLI application,
    # falling back to the applicant's username so _resolve_wallet_row_licensee_id can find
    # the correct wallet row.
    nli_app = getattr(application, "new_license_application", None)
    nli_license_id = None
    if nli_app:
        try:
            from django.contrib.contenttypes.models import ContentType as CT
            from models.masters.license.models import License as Lic
            from models.transactional.new_license_application.models import NewLicenseApplication as NLI
            nli_ct = CT.objects.get_for_model(NLI)
            nli_lic = (
                Lic.objects.filter(
                    source_type="new_license_application",
                    source_content_type=nli_ct,
                    source_object_id=str(nli_app.pk),
                )
                .order_by("-issue_date", "-license_id")
                .first()
            )
            if nli_lic:
                nli_license_id = str(nli_lic.license_id).strip()
        except Exception:
            pass

    wallet_licensee_id = nli_license_id or str(getattr(request.user, "username", "") or "").strip()

    txn_id = secrets.token_hex(12).upper()
    try:
        debit_wallet_balance(
            transaction_id=txn_id,
            licensee_id=wallet_licensee_id,
            wallet_type="license_fee",
            head_of_account=COMMON_LICENSE_FEE_HOA,
            amount=amount,
            user_id=str(getattr(request.user, "username", "") or "").strip(),
            remarks=f"Salesman/Barman registration fee paid for {application.application_id}",
            reference_no=application.application_id,
        )
    except Exception as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    # Advance to final approved stage if configured.
    try:
        if not application.is_approved:
            application.is_approved = True
        if hasattr(application, "is_print_fee_paid") and not application.is_print_fee_paid:
            application.is_print_fee_paid = True
        application.save(update_fields=["is_approved", "is_print_fee_paid"])

        approved_stage = (
            application.workflow.stages.filter(name__iexact="approved").order_by("id").first()
            if getattr(application, "workflow_id", None)
            else None
        )
        if approved_stage:
            WorkflowService.advance_stage(
                application=application,
                user=request.user,
                target_stage=approved_stage,
                context={"action": "PAY"},
                remarks="Salesman/Barman registration fee paid via wallet",
            )
            application.refresh_from_db()
    except Exception:
        # Payment succeeded; keep stage as-is if workflow advance fails.
        pass

    return Response({"success": True, "transaction_id": txn_id})


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


@permission_classes([HasAppPermission('salesman_barman_registration', 'view'), HasStagePermission])
@api_view(['GET'])
def list_salesman_barman(request):
    role = _normalize_role(request.user.role.name if request.user.role else None)

    if role in ["site_admin"]:
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


@permission_classes([HasAppPermission('salesman_barman_registration', 'view')])
@api_view(['GET'])
def salesman_barman_detail(request, application_id):
    app = get_object_or_404(SalesmanBarmanModel, application_id=application_id)
    serializer = SalesmanBarmanSerializer(app)
    return Response(serializer.data)


# Dashboard Counts
@permission_classes([HasAppPermission('salesman_barman_registration', 'view'), HasStagePermission])
@api_view(['GET'])
def dashboard_counts(request):
    role = _normalize_role(request.user.role.name if request.user.role else None)
    workflow_id = WORKFLOW_IDS['SALESMAN_BARMAN']
    stage_sets = _get_stage_sets(workflow_id)
    all_qs = SalesmanBarmanModel.objects.all()

    if role == 'licensee':
        base_qs = SalesmanBarmanModel.objects.filter(applicant=request.user)
        applied_stages = set(stage_sets['initial'])
        objection_stages = set(stage_sets['objection'])
        pending_stages = _get_in_progress_stage_names(stage_sets) - applied_stages - objection_stages
        # The licensee UI does not surface an "Applied" tile; treat initial-stage apps as pending.
        pending_for_ui = pending_stages | applied_stages
        return Response({
            "applied": base_qs.filter(current_stage__name__in=applied_stages).count(),
            "pending": base_qs.filter(current_stage__name__in=pending_for_ui).count(),
            "objection": base_qs.filter(current_stage__name__in=objection_stages).count(),
            "approved": base_qs.filter(current_stage__name__in=stage_sets['approved']).count(),
            "rejected": base_qs.filter(current_stage__name__in=stage_sets['rejected']).count(),
        })

    if role in ['site_admin']:
        applied_stages = set(stage_sets['initial'])
        pending_stages = _get_in_progress_stage_names(stage_sets) - applied_stages
        pending_for_ui = pending_stages | applied_stages
        return Response({
            "applied": all_qs.filter(current_stage__name__in=applied_stages).count(),
            "pending": all_qs.filter(current_stage__name__in=pending_for_ui).count(),
            "approved": all_qs.filter(current_stage__name__in=stage_sets['approved']).count(),
            "rejected": all_qs.filter(current_stage__name__in=stage_sets['rejected']).count(),
        })

    role_stage_names = _get_role_stage_names(request.user, workflow_id)
    if not role_stage_names:
        return Response({"detail": "Invalid role"}, status=status.HTTP_400_BAD_REQUEST)

    from django.db.models import OuterRef, Subquery, IntegerField, Q

    content_type = ContentType.objects.get_for_model(SalesmanBarmanModel)
    txn_qs = (
        WorkflowTransaction.objects.filter(content_type=content_type, object_id=OuterRef('application_id'))
        .order_by('-timestamp')
    )
    last_actor_role_id = Subquery(txn_qs.values('performed_by__role_id')[:1], output_field=IntegerField())
    prev_actor_role_id = Subquery(txn_qs.values('performed_by__role_id')[1:2], output_field=IntegerField())

    role_id = getattr(getattr(request.user, 'role', None), 'id', None)
    pending_stages = set(role_stage_names)
    rejected_stages = set(stage_sets['rejected'])
    objection_stages = set(stage_sets['objection'])

    pending_count = all_qs.filter(current_stage__name__in=pending_stages).count()
    approved_count = (
        all_qs.exclude(current_stage__name__in=pending_stages | rejected_stages | objection_stages)
        .annotate(_last_actor_role_id=last_actor_role_id)
        .filter(_last_actor_role_id=role_id)
        .count()
    )
    rejected_count = (
        all_qs.filter(current_stage__name__in=rejected_stages)
        .annotate(_last_actor_role_id=last_actor_role_id, _prev_actor_role_id=prev_actor_role_id)
        .filter(Q(_prev_actor_role_id=role_id) | Q(_last_actor_role_id=role_id))
        .count()
    )
    objection_count = (
        all_qs.filter(current_stage__name__in=objection_stages)
        .annotate(_last_actor_role_id=last_actor_role_id)
        .filter(_last_actor_role_id=role_id)
        .count()
    )

    return Response({
        "pending": pending_count,
        "approved": approved_count,
        "rejected": rejected_count,
        "objection": objection_count,
    })

@permission_classes([HasAppPermission('salesman_barman_registration', 'view'), HasStagePermission])
@api_view(['GET'])
@parser_classes([JSONParser])
def application_group(request):
    role = _normalize_role(request.user.role.name if request.user.role else None)
    workflow_id = WORKFLOW_IDS['SALESMAN_BARMAN']
    stage_sets = _get_stage_sets(workflow_id)
    all_qs = SalesmanBarmanModel.objects.all()

    if role == 'licensee':
        base_qs = SalesmanBarmanModel.objects.filter(applicant=request.user)
        applied_stages = set(stage_sets['initial'])
        objection_stages = set(stage_sets['objection'])
        pending_stages = _get_in_progress_stage_names(stage_sets) - applied_stages - objection_stages
        result = {
            "applied": SalesmanBarmanSerializer(
                base_qs.filter(current_stage__name__in=applied_stages),
                many=True
            ).data,
            "pending": SalesmanBarmanSerializer(
                base_qs.filter(current_stage__name__in=pending_stages),
                many=True
            ).data,
            "objection": SalesmanBarmanSerializer(
                base_qs.filter(current_stage__name__in=objection_stages),
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

    if role in ['site_admin']:
        applied_stages = set(stage_sets['initial'])
        pending_stages = _get_in_progress_stage_names(stage_sets) - applied_stages
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
        from django.db.models import OuterRef, Subquery, IntegerField, Q

        content_type = ContentType.objects.get_for_model(SalesmanBarmanModel)
        txn_qs = (
            WorkflowTransaction.objects.filter(content_type=content_type, object_id=OuterRef('application_id'))
            .order_by('-timestamp')
        )
        last_actor_role_id = Subquery(txn_qs.values('performed_by__role_id')[:1], output_field=IntegerField())
        prev_actor_role_id = Subquery(txn_qs.values('performed_by__role_id')[1:2], output_field=IntegerField())

        role_id = getattr(getattr(request.user, 'role', None), 'id', None)
        pending_stages = set(role_stage_names)
        rejected_stages = set(stage_sets['rejected'])
        objection_stages = set(stage_sets['objection'])

        approved_qs = (
            all_qs.exclude(current_stage__name__in=pending_stages | rejected_stages | objection_stages)
            .annotate(_last_actor_role_id=last_actor_role_id)
            .filter(_last_actor_role_id=role_id)
        )
        rejected_qs = (
            all_qs.filter(current_stage__name__in=rejected_stages)
            .annotate(_last_actor_role_id=last_actor_role_id, _prev_actor_role_id=prev_actor_role_id)
            .filter(Q(_prev_actor_role_id=role_id) | Q(_last_actor_role_id=role_id))
        )
        objection_qs = (
            all_qs.filter(current_stage__name__in=objection_stages)
            .annotate(_last_actor_role_id=last_actor_role_id)
            .filter(_last_actor_role_id=role_id)
        )

        return Response({
            "pending": SalesmanBarmanSerializer(
                all_qs.filter(current_stage__name__in=pending_stages), many=True
            ).data,
            "approved": SalesmanBarmanSerializer(approved_qs, many=True).data,
            "rejected": SalesmanBarmanSerializer(rejected_qs, many=True).data,
            "objection": SalesmanBarmanSerializer(objection_qs, many=True).data,
        })

    return Response({"detail": "Invalid role"}, status=status.HTTP_400_BAD_REQUEST)
