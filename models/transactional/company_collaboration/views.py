import json
from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404
from rest_framework import permissions, status
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.exceptions import PermissionDenied
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from auth.roles.permissions import HasAppPermission
from auth.workflow.models import Workflow, WorkflowStage
from auth.workflow.permissions import HasStagePermission
from auth.workflow.services import WorkflowService
from auth.workflow.models import Transaction as WorkflowTransaction
from django.db.models import OuterRef, Exists
from django.contrib.contenttypes.models import ContentType
from models.transactional.dashboard_cache import dashboard_counts_cache

from .models import CompanyCollaboration
from .serializers import CompanyCollaborationSerializer

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

JSON_FIELDS = ['selected_brand_ids', 'selected_brands', 'fee_structure', 'overview_summary']

# Stage name constants — must match exactly what is in workflow_workflowstage
STAGE_APPLICANT_APPLIED             = 'applicant_applied'
STAGE_PERMIT_SECTION                = 'permit_section'
STAGE_PERMIT_SECTION_OBJECTION      = 'permit_section_objection'
STAGE_COMMISSIONER                  = 'commissioner'
STAGE_COMMISSIONER_OBJECTION        = 'commissioner_objection'
STAGE_AWAITING_PAYMENT              = 'awaiting_payment'
STAGE_FINAL_COMMISSIONER_REVIEW     = 'final_commissioner_review'
STAGE_APPROVED                      = 'approved'
STAGE_REJECTED                      = 'rejected'

# Stages that are considered "in review" by an officer (application moving forward)
OFFICER_PENDING_STAGES = [
    STAGE_PERMIT_SECTION,
    STAGE_COMMISSIONER,
    STAGE_FINAL_COMMISSIONER_REVIEW,
]

# Stages where the applicant needs to respond to an objection
OBJECTION_STAGES = [
    STAGE_PERMIT_SECTION_OBJECTION,
    STAGE_COMMISSIONER_OBJECTION,
]

# Role name -> (pending_stages, approved_stages, rejected_stages)
ROLE_STAGE_MAP = {
    'permit_section': {
        'pending':  [STAGE_PERMIT_SECTION, STAGE_PERMIT_SECTION_OBJECTION],
        'approved': [STAGE_COMMISSIONER],
        'rejected': [STAGE_REJECTED],
    },
    'commissioner': {
        'pending':  [STAGE_COMMISSIONER, STAGE_COMMISSIONER_OBJECTION, STAGE_FINAL_COMMISSIONER_REVIEW],
        'approved': [STAGE_AWAITING_PAYMENT, STAGE_APPROVED],
        'rejected': [STAGE_REJECTED],
    },
    'licensee': {
        'pending':  [STAGE_APPLICANT_APPLIED, STAGE_AWAITING_PAYMENT,
                     STAGE_PERMIT_SECTION_OBJECTION, STAGE_COMMISSIONER_OBJECTION],
        'approved': [STAGE_APPROVED],
        'rejected': [STAGE_REJECTED],
    },
}

# Valid workflow transitions:
# current_stage_name -> action -> target_stage_name
WORKFLOW_TRANSITIONS = {
    STAGE_APPLICANT_APPLIED: {
        'FORWARD': STAGE_PERMIT_SECTION,
        'REJECT':  STAGE_REJECTED,
    },
    STAGE_PERMIT_SECTION: {
        'FORWARD':         STAGE_COMMISSIONER,
        'REJECT':          STAGE_REJECTED,
        'RAISE_OBJECTION': STAGE_PERMIT_SECTION_OBJECTION,
    },
    STAGE_PERMIT_SECTION_OBJECTION: {
        'RESPOND_OBJECTION': STAGE_PERMIT_SECTION,
        'WITHDRAW':          STAGE_REJECTED,
    },
    STAGE_COMMISSIONER: {
        'APPROVE':         STAGE_AWAITING_PAYMENT,
        'REJECT':          STAGE_REJECTED,
        'RAISE_OBJECTION': STAGE_COMMISSIONER_OBJECTION,
    },
    STAGE_COMMISSIONER_OBJECTION: {
        'RESPOND_OBJECTION': STAGE_COMMISSIONER,
        'WITHDRAW':          STAGE_REJECTED,
    },
    STAGE_AWAITING_PAYMENT: {
        'PAY': STAGE_FINAL_COMMISSIONER_REVIEW,
    },
    STAGE_FINAL_COMMISSIONER_REVIEW: {
        'APPROVE': STAGE_APPROVED,
        'REJECT':  STAGE_REJECTED,
    },
}

# Which roles are allowed to perform which actions at which stages
ROLE_ACTION_PERMISSIONS = {
    'permit_section': {
        STAGE_PERMIT_SECTION: ['FORWARD', 'REJECT', 'RAISE_OBJECTION'],
    },
    'commissioner': {
        STAGE_COMMISSIONER:              ['APPROVE', 'REJECT', 'RAISE_OBJECTION'],
        STAGE_FINAL_COMMISSIONER_REVIEW: ['APPROVE', 'REJECT'],
    },
    'licensee': {
        STAGE_APPLICANT_APPLIED:         ['FORWARD'],
        STAGE_PERMIT_SECTION_OBJECTION:  ['RESPOND_OBJECTION', 'WITHDRAW'],
        STAGE_COMMISSIONER_OBJECTION:    ['RESPOND_OBJECTION', 'WITHDRAW'],
        STAGE_AWAITING_PAYMENT:          ['PAY'],
    },
    'site_admin': {
        # Admin can trigger any action for support / testing purposes
        '__all__': ['FORWARD', 'APPROVE', 'REJECT', 'RAISE_OBJECTION', 'RESPOND_OBJECTION', 'WITHDRAW', 'PAY'],
    },
    'single_window': {
        STAGE_APPLICANT_APPLIED: ['FORWARD', 'REJECT'],
    },
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalize_role(role_name):
    if not role_name:
        return None
    normalized = str(role_name).strip().lower().replace('-', '_').replace(' ', '_')
    aliases = {
        'license_user':       'licensee',
        'licensee_user':      'licensee',
        'singlewindow':       'single_window',
        'siteadmin':          'site_admin',
        'permitsection':      'permit_section',
        'permit_excise':      'permit_section',
        'permitexcise':       'permit_section',
        'permit_excise_section': 'permit_section',
        'permit_excise_officer': 'permit_section',
        'deputycommissioner': 'deputy_commissioner',
        'deputy_commissioner_excise': 'deputy_commissioner',
        'deputycommissionerexcise': 'deputy_commissioner',
        'joint_commissioner': 'deputy_commissioner',
        'jointcommissioner': 'deputy_commissioner',
        'commissioner_excise': 'commissioner',
        'commissionerexcise': 'commissioner',
    }
    return aliases.get(normalized, normalized)


def _normalize_json_payload(data: dict) -> dict:
    normalized = {key: data.get(key) for key in data.keys()}
    for field in JSON_FIELDS:
        value = normalized.get(field)
        if isinstance(value, str) and value.strip():
            try:
                normalized[field] = json.loads(value)
            except json.JSONDecodeError:
                pass
    return normalized


def _resolve_workflow() -> Workflow:
    workflow = Workflow.objects.filter(name='Company Collaboration').first()
    if not workflow:
        raise Http404(
            "Workflow 'Company Collaboration' not found. "
            "Please create it in the Django admin before accepting applications."
        )
    return workflow


def _get_stage(workflow: Workflow, stage_name: str) -> WorkflowStage:
    """Fetch a WorkflowStage by name or raise a clear 400 error."""
    stage = workflow.stages.filter(name=stage_name).first()
    if not stage:
        raise ValueError(
            f"Stage '{stage_name}' not found in workflow '{workflow.name}'. "
            "Check your workflow configuration."
        )
    return stage


def _check_action_permission(role: str, current_stage_name: str, action: str) -> bool:
    """Return True if the given role may perform action at the current stage."""
    perms = ROLE_ACTION_PERMISSIONS.get(role, {})
    # Site admin can do anything
    if '__all__' in perms and action in perms['__all__']:
        return True
    allowed_actions = perms.get(current_stage_name, [])
    return action in allowed_actions


class HasCompanyCollaborationViewPermission(permissions.BasePermission):
    """
    Accept the dedicated company_collaboration permission when present, and
    fall back to company_registration view access for existing role configs.
    """

    def has_permission(self, request, view):
        permission_labels = ('company_collaboration', 'company_registration')

        for label in permission_labels:
            permission = HasAppPermission(label, 'view')
            try:
                if permission.has_permission(request, view):
                    return True
            except PermissionDenied as exc:
                if exc.get_codes() != 'cannot_view':
                    raise

        raise PermissionDenied(detail='Cannot view company_collaboration', code='cannot_view')


# ---------------------------------------------------------------------------
# Application creation
# ---------------------------------------------------------------------------

def _create_application(request) -> Response:
    payload = _normalize_json_payload(request.data)
    serializer = CompanyCollaborationSerializer(data=payload)
    serializer.is_valid(raise_exception=True)

    with transaction.atomic():
        workflow = _resolve_workflow()
        initial_stage = workflow.stages.filter(is_initial=True).first()
        if not initial_stage:
            return Response(
                {'detail': 'Workflow "Company Collaboration" has no initial stage (is_initial=True).'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        fin_year = CompanyCollaboration.generate_fin_year()
        prefix = f"CCOL/{fin_year}"
        last_app = (
            CompanyCollaboration.objects
            .filter(application_id__startswith=prefix)
            .select_for_update()
            .order_by('-application_id')
            .first()
        )
        last_number = 0
        if last_app:
            try:
                last_number = int(last_app.application_id.split('/')[-1])
            except (ValueError, IndexError):
                last_number = 0
        application_id = f"{prefix}/{str(last_number + 1).zfill(4)}"

        application = serializer.save(
            workflow=workflow,
            current_stage=initial_stage,
            application_id=application_id,
            applicant=request.user,
        )

        WorkflowService.submit_application(
            application=application,
            user=request.user,
            remarks='Company collaboration application submitted',
        )

    fresh = CompanyCollaboration.objects.get(pk=application.pk)
    return Response(CompanyCollaborationSerializer(fresh).data, status=status.HTTP_201_CREATED)


# ---------------------------------------------------------------------------
# POST /apply/
# ---------------------------------------------------------------------------

@api_view(['POST'])
@parser_classes([MultiPartParser, FormParser, JSONParser])
@permission_classes([HasStagePermission])
def create_company_collaboration(request):
    try:
        return _create_application(request)
    except Http404 as exc:
        return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as exc:
        return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)


# ---------------------------------------------------------------------------
# GET /list/
# ---------------------------------------------------------------------------

@api_view(['GET'])
@permission_classes([HasCompanyCollaborationViewPermission, HasStagePermission])
def list_company_collaborations(request):
    role = _normalize_role(request.user.role.name if request.user.role else None)

    if role in ['single_window', 'site_admin']:
        applications = CompanyCollaboration.objects.all()
    elif role == 'licensee':
        applications = CompanyCollaboration.objects.filter(applicant=request.user)
    else:
        # Officer roles: only see applications currently sitting at their stage(s)
        stages = ROLE_STAGE_MAP.get(role, {})
        all_officer_stages = (
            stages.get('pending', []) +
            stages.get('approved', []) +
            stages.get('rejected', [])
        )
        if all_officer_stages:
            applications = CompanyCollaboration.objects.filter(
                current_stage__name__in=all_officer_stages
            ).distinct()
        else:
            applications = CompanyCollaboration.objects.none()

    serializer = CompanyCollaborationSerializer(applications, many=True)
    return Response(serializer.data)


# ---------------------------------------------------------------------------
# GET /detail/<application_id>/
# ---------------------------------------------------------------------------

@api_view(['GET'])
@permission_classes([HasCompanyCollaborationViewPermission, HasStagePermission])
def company_collaboration_detail(request, application_id):
    application = get_object_or_404(CompanyCollaboration, application_id=application_id)
    return Response(CompanyCollaborationSerializer(application).data)


# ---------------------------------------------------------------------------
# POST /workflow-action/<application_id>/
# ---------------------------------------------------------------------------

@api_view(['POST'])
@parser_classes([JSONParser])
@permission_classes([HasCompanyCollaborationViewPermission, HasStagePermission])
def workflow_action(request, application_id):
    """
    Perform a workflow transition on a Company Collaboration application.

    Request body:
        {
            "action":  "FORWARD" | "APPROVE" | "REJECT" | "RAISE_OBJECTION"
                       | "RESPOND_OBJECTION" | "WITHDRAW",
            "remarks": "Optional free-text remarks"
        }

    Workflow path (happy path):
        applicant_applied
          → [FORWARD by single_window / admin]
        permit_section
          → [FORWARD by permit_section]
        deputy_commissioner
          → [FORWARD by deputy_commissioner]
        commissioner
          → [APPROVE by commissioner]
        approved  ✓

    Objection path:
        <officer stage>
          → [RAISE_OBJECTION by officer]
        <objection stage>
          → [RESPOND_OBJECTION by licensee]  → back to officer stage
          → [WITHDRAW by licensee]            → rejected

    Rejection: any officer or admin can reject at their stage.
    """
    action  = str(request.data.get('action', '')).strip().upper()
    remarks = str(request.data.get('remarks', '')).strip()

    if not action:
        return Response({'detail': "'action' is required."}, status=status.HTTP_400_BAD_REQUEST)

    application = get_object_or_404(CompanyCollaboration, application_id=application_id)

    # ── Guard: already terminal ───────────────────────────────────────────
    current_stage_name = application.current_stage.name
    if current_stage_name in (STAGE_APPROVED, STAGE_REJECTED):
        return Response(
            {'detail': f"Application is already in a terminal stage: '{current_stage_name}'."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # ── Role check ────────────────────────────────────────────────────────
    role = _normalize_role(request.user.role.name if request.user.role else None)
    if not _check_action_permission(role, current_stage_name, action):
        return Response(
            {
                'detail': (
                    f"Role '{role}' is not permitted to perform '{action}' "
                    f"at stage '{current_stage_name}'."
                )
            },
            status=status.HTTP_403_FORBIDDEN,
        )

    # ── Determine target stage ────────────────────────────────────────────
    stage_transitions = WORKFLOW_TRANSITIONS.get(current_stage_name, {})
    target_stage_name = stage_transitions.get(action)

    if not target_stage_name:
        return Response(
            {
                'detail': (
                    f"Action '{action}' is not valid at stage '{current_stage_name}'. "
                    f"Valid actions: {list(stage_transitions.keys())}."
                )
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # ── Apply transition ──────────────────────────────────────────────────
    try:
        with transaction.atomic():
            target_stage = _get_stage(application.workflow, target_stage_name)

            application.current_stage = target_stage
            if action == 'APPROVE':
                application.is_approved = True
            elif action in ('REJECT', 'WITHDRAW'):
                application.is_approved = False

            application.save()

            # Record the transaction in the audit trail
            WorkflowService.record_transaction(
                application=application,
                user=request.user,
                action=action,
                remarks=remarks or f"{action.replace('_', ' ').title()} by {role}",
            )

    except ValueError as exc:
        return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as exc:
        return Response({'detail': str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    fresh = CompanyCollaboration.objects.get(pk=application.pk)
    return Response(
        {
            'detail': f"Action '{action}' applied successfully.",
            'application': CompanyCollaborationSerializer(fresh).data,
        }
    )


# ---------------------------------------------------------------------------
# GET /dashboard-counts/
# ---------------------------------------------------------------------------

@api_view(['GET'])
@permission_classes([HasCompanyCollaborationViewPermission, HasStagePermission])
@dashboard_counts_cache("company_collaboration")
def dashboard_counts(request):
    role = _normalize_role(request.user.role.name if request.user.role else None)
    base_qs = CompanyCollaboration.objects.all()

    # Filter by month and year if provided
    month = request.query_params.get('month')
    year = request.query_params.get('year')
    if month:
        base_qs = base_qs.filter(created_at__month=month)
    if year:
        base_qs = base_qs.filter(created_at__year=year)

    # ── Permit Section ───────────────────────────────────────────────────
    if role == 'permit_section':
        counts = {
            'applied': base_qs.count(),
            'pending':  base_qs.filter(current_stage__name__in=[STAGE_PERMIT_SECTION, STAGE_PERMIT_SECTION_OBJECTION]).count(),
            'approved': base_qs.filter(current_stage__name__in=[
                STAGE_COMMISSIONER, STAGE_COMMISSIONER_OBJECTION, 
                STAGE_AWAITING_PAYMENT, STAGE_FINAL_COMMISSIONER_REVIEW, STAGE_APPROVED
            ]).count(),
            'rejected': base_qs.filter(current_stage__name=STAGE_REJECTED).count(),
            'objection': base_qs.filter(current_stage__name=STAGE_PERMIT_SECTION_OBJECTION).count(),
            'awaiting_payment': base_qs.filter(current_stage__name=STAGE_AWAITING_PAYMENT).count(),
        }

    # ── Commissioner ─────────────────────────────────────────────────────
    elif role == 'commissioner':
        counts = {
            'applied': base_qs.count(),
            'pending':  base_qs.filter(current_stage__name__in=[STAGE_COMMISSIONER, STAGE_COMMISSIONER_OBJECTION, STAGE_FINAL_COMMISSIONER_REVIEW]).count(),
            'approved': base_qs.filter(current_stage__name__in=[STAGE_AWAITING_PAYMENT, STAGE_APPROVED]).count(),
            'rejected': base_qs.filter(current_stage__name=STAGE_REJECTED).count(),
            'objection': base_qs.filter(current_stage__name=STAGE_COMMISSIONER_OBJECTION).count(),
            'awaiting_payment': base_qs.filter(current_stage__name=STAGE_AWAITING_PAYMENT).count(),
        }

    # ── Applicant / licensee ─────────────────────────────────────────────
    elif role == 'licensee':
        mine = base_qs.filter(applicant=request.user)
        counts = {
            'applied':   mine.count(),
            'pending':   mine.filter(current_stage__name__in=[STAGE_APPLICANT_APPLIED] + OFFICER_PENDING_STAGES).count(),
            'objection': mine.filter(current_stage__name__in=OBJECTION_STAGES).count(),
            'approved':  mine.filter(current_stage__name=STAGE_APPROVED, is_approved=True).count(),
            'rejected':  mine.filter(current_stage__name=STAGE_REJECTED).count(),
            'awaiting_payment': mine.filter(current_stage__name=STAGE_AWAITING_PAYMENT).count(),
        }

    # ── Admins, single window, and fallbacks ─────────────────────────────
    else:
        counts = {
            'applied':   base_qs.count(),
            'pending':   base_qs.filter(current_stage__name__in=OFFICER_PENDING_STAGES).count(),
            'objection': base_qs.filter(current_stage__name__in=OBJECTION_STAGES).count(),
            'approved':  base_qs.filter(current_stage__name=STAGE_APPROVED, is_approved=True).count(),
            'rejected':  base_qs.filter(current_stage__name=STAGE_REJECTED).count(),
            'awaiting_payment': base_qs.filter(current_stage__name=STAGE_AWAITING_PAYMENT).count(),
        }

    return Response(counts)


# ---------------------------------------------------------------------------
# GET /list-by-status/
# ---------------------------------------------------------------------------

@api_view(['GET'])
@permission_classes([HasCompanyCollaborationViewPermission, HasStagePermission])
@parser_classes([JSONParser])
def application_group(request):
    role = _normalize_role(request.user.role.name if request.user.role else None)
    base_qs = CompanyCollaboration.objects

    def _serialize(qs):
        return CompanyCollaborationSerializer(qs, many=True).data

    # ── Officer roles ────────────────────────────────────────────────────
    if role in ROLE_STAGE_MAP:
        stages = ROLE_STAGE_MAP[role]
        
        content_type = ContentType.objects.get_for_model(CompanyCollaboration)
        role_id = getattr(getattr(request.user, 'role', None), 'id', None)
        
        acted_by_role = Exists(
            WorkflowTransaction.objects.filter(
                content_type=content_type, 
                object_id=OuterRef('application_id'),
                performed_by__role_id=role_id
            )
        )
        
        pending_stages = stages['pending']
        
        return Response({
            'pending':  _serialize(base_qs.filter(current_stage__name__in=pending_stages)),
            'approved': _serialize(
                base_qs.exclude(current_stage__name__in=pending_stages + [STAGE_REJECTED])
                .annotate(_acted_by_role=acted_by_role)
                .filter(_acted_by_role=True)
            ),
            'rejected': _serialize(
                base_qs.filter(current_stage__name=STAGE_REJECTED)
                .annotate(_acted_by_role=acted_by_role)
                .filter(_acted_by_role=True)
            ),
        })

    # ── Applicant / licensee ─────────────────────────────────────────────
    if role == 'licensee':
        mine = base_qs.filter(applicant=request.user)
        return Response({
            'applied':   _serialize(mine.filter(current_stage__name__in=OFFICER_PENDING_STAGES)),
            'objection': _serialize(mine.filter(current_stage__name__in=OBJECTION_STAGES)),
            'approved':  _serialize(mine.filter(current_stage__name=STAGE_APPROVED)),
            'rejected':  _serialize(mine.filter(current_stage__name=STAGE_REJECTED)),
        })

    # ── Admin / single window ────────────────────────────────────────────
    if role in ['site_admin', 'single_window']:
        return Response({
            'applied':   _serialize(base_qs.filter(current_stage__name=STAGE_APPLICANT_APPLIED)),
            'in_review': _serialize(base_qs.filter(current_stage__name__in=OFFICER_PENDING_STAGES)),
            'objection': _serialize(base_qs.filter(current_stage__name__in=OBJECTION_STAGES)),
            'approved':  _serialize(base_qs.filter(current_stage__name=STAGE_APPROVED)),
            'rejected':  _serialize(base_qs.filter(current_stage__name=STAGE_REJECTED)),
        })

    return Response({
        "applied": [],
        "pending": [],
        "objection": [],
        "approved": [],
        "rejected": []
    })


# ---------------------------------------------------------------------------
# POST /pay-fee/<application_id>/
# ---------------------------------------------------------------------------

@api_view(['POST'])
@permission_classes([HasCompanyCollaborationViewPermission, HasStagePermission])
def pay_collaboration_fee(request, application_id):
    """
    Wallet debit for Company Collaboration fee (COMP_COLLAB_FEE).
    On success, advance workflow from awaiting_payment → final_commissioner_review.
    """
    import secrets
    from decimal import Decimal
    from models.transactional.wallet.wallet_service import debit_wallet_balance
    from models.transactional.wallet.wallet_initializer import _resolve_hoa_code

    application = get_object_or_404(CompanyCollaboration, application_id=application_id)

    # Verify user is licensee and owns this application
    role = _normalize_role(request.user.role.name if request.user.role else None)
    if role not in ('licensee', 'site_admin'):
        return Response(
            {'detail': 'Only licensees can pay the collaboration fee.'},
            status=status.HTTP_403_FORBIDDEN,
        )
    if role == 'licensee' and application.applicant != request.user:
        return Response({'detail': 'Not found or not authorized.'}, status=status.HTTP_404_NOT_FOUND)

    # Only allow payment when application is awaiting_payment
    current_stage_name = application.current_stage.name if application.current_stage else ''
    if current_stage_name != STAGE_AWAITING_PAYMENT:
        return Response(
            {'detail': f"Application is in stage '{current_stage_name}', not '{STAGE_AWAITING_PAYMENT}'."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Fetch fee amount from masters_fixedfee
    try:
        from django.apps import apps
        FixedFee = apps.get_model('core', 'MasterFixedFee')
        fee_obj = FixedFee.objects.filter(fee_code='COMP_COLLAB_FEE', is_active=True).first()
        amount = fee_obj.amount if fee_obj else Decimal('25000.00')
    except Exception:
        amount = Decimal('25000.00')

    # Debit from license_fee wallet
    wallet_licensee_id = str(getattr(request.user, 'username', '') or '').strip()
    license_fee_hoa = _resolve_hoa_code(module_type='other', wallet_type='license_fee')
    txn_id = secrets.token_hex(12).upper()

    try:
        debit_wallet_balance(
            transaction_id=txn_id,
            licensee_id=wallet_licensee_id,
            wallet_type='license_fee',
            head_of_account=license_fee_hoa,
            amount=amount,
            user_id=wallet_licensee_id,
            remarks=f'Company Collaboration fee paid for {application.application_id}',
            reference_no=application.application_id,
        )
    except Exception as exc:
        return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    # Advance to final_commissioner_review
    try:
        with transaction.atomic():
            target_stage = _get_stage(application.workflow, STAGE_FINAL_COMMISSIONER_REVIEW)
            application.current_stage = target_stage
            application.save()

            WorkflowService.record_transaction(
                application=application,
                user=request.user,
                action='PAY',
                remarks=f'Collaboration fee paid via license wallet. Trans ID: {txn_id}',
            )
    except ValueError as exc:
        return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as exc:
        return Response(
            {'detail': f'Payment succeeded but workflow advance failed: {str(exc)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    fresh = CompanyCollaboration.objects.get(pk=application.pk)
    return Response({
        'success': True,
        'transaction_id': txn_id,
        'application': CompanyCollaborationSerializer(fresh).data,
    })

