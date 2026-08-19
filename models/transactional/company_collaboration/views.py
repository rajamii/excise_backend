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
        'distributor': 'licensee',
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

        # ── Auto-create Company Registration ─────────────────────────────
        try:
            from models.transactional.company_registration.models import CompanyRegistration as RegCompany
            from auth.workflow.models import StagePermission as RegStagePermission
            
            reg_workflow = Workflow.objects.get(name="Company Registration")
            reg_initial_stage = reg_workflow.stages.get(is_initial=True)
            
            reg_fin_year = RegCompany.generate_fin_year()
            reg_prefix = f"COMP/{reg_fin_year}"
            reg_last_app = RegCompany.objects.filter(
                application_id__startswith=reg_prefix
            ).select_for_update().order_by('-application_id').first()

            reg_last_number = int(reg_last_app.application_id.split('/')[-1]) if reg_last_app else 0
            reg_new_number = str(reg_last_number + 1).zfill(4)
            reg_new_application_id = f"{reg_prefix}/{reg_new_number}"

            # Extract fields safely
            members_data = []
            import json
            raw_members = request.data.get('members')
            if raw_members:
                try:
                    members_data = json.loads(raw_members) if isinstance(raw_members, str) else raw_members
                except Exception:
                    pass
            
            member_name = ""
            member_designation = ""
            member_mobile = 0
            member_email = ""
            member_address = ""
            if members_data and len(members_data) > 0:
                first_m = members_data[0]
                member_name = first_m.get('memberName') or first_m.get('member_name') or ""
                member_designation = first_m.get('memberDesignation') or first_m.get('member_designation') or ""
                member_mobile = first_m.get('memberMobileNumber') or first_m.get('member_mobile_number') or 0
                member_email = first_m.get('memberEmailId') or first_m.get('member_email_id') or ""
                member_address = first_m.get('memberAddress') or first_m.get('member_address') or ""

            pin_code = 0
            try: pin_code = int(request.data.get('pinCode') or request.data.get('pin_code') or 0)
            except Exception: pass
            
            mobile = 0
            try: mobile = int(payload.get('brand_owner_mobile') or 0)
            except Exception: pass

            try: member_mobile = int(member_mobile or 0)
            except Exception: pass

            # Files copy
            undertaking_file = request.FILES.get('undertaking')
            excise_license_file = request.FILES.get('excise_license')
            deed_of_partnership_file = request.FILES.get('deed_of_partnership')
            memorandum_of_association_file = request.FILES.get('memorandum_of_association')

            # Create RegCompany
            reg_app = RegCompany.objects.create(
                application_id=reg_new_application_id,
                workflow=reg_workflow,
                current_stage=reg_initial_stage,
                applicant=request.user,
                brand_type=request.data.get('brandType') or request.data.get('brand_type') or 'Bottled in Sikkim (Collaboration)',
                license=request.data.get('license') or request.data.get('bottlerId') or '',
                company_name=payload.get('brand_owner_name') or '',
                country=request.data.get('country') or 'India',
                state=request.data.get('state') or 'Sikkim',
                factory_address=payload.get('brand_owner_factory_address') or '',
                pin_code=pin_code,
                company_mobile_number=mobile,
                company_email_id=payload.get('brand_owner_email') or '',
                member_name=member_name,
                member_designation=member_designation,
                member_mobile_number=member_mobile,
                member_email_id=member_email,
                member_address=member_address,
                members=members_data,
                undertaking=undertaking_file,
                excise_license=excise_license_file,
                deed_of_partnership=deed_of_partnership_file,
                memorandum_of_association=memorandum_of_association_file
            )

            # Submit RegCompany application in workflow
            WorkflowService.submit_application(
                application=reg_app,
                user=request.user,
                remarks="Application submitted via Company Collaboration",
            )
            
        except Exception as e:
            print("Error creating auto company registration:", e)
            raise e

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
        pending = base_qs.filter(current_stage__name__in=[STAGE_PERMIT_SECTION, STAGE_PERMIT_SECTION_OBJECTION]).count()
        approved = base_qs.filter(current_stage__name__in=[
            STAGE_COMMISSIONER, STAGE_COMMISSIONER_OBJECTION, 
            STAGE_AWAITING_PAYMENT, STAGE_FINAL_COMMISSIONER_REVIEW, STAGE_APPROVED
        ]).count()
        rejected = base_qs.filter(current_stage__name=STAGE_REJECTED).count()
        objection = base_qs.filter(current_stage__name=STAGE_PERMIT_SECTION_OBJECTION).count()
        awaiting_payment = base_qs.filter(current_stage__name=STAGE_AWAITING_PAYMENT).count()
        counts = {
            'applied': pending + approved + rejected,
            'pending':  pending,
            'approved': approved,
            'rejected': rejected,
            'objection': objection,
            'awaiting_payment': awaiting_payment,
        }

    # ── Commissioner ─────────────────────────────────────────────────────
    elif role == 'commissioner':
        pending = base_qs.filter(current_stage__name__in=[STAGE_COMMISSIONER, STAGE_COMMISSIONER_OBJECTION, STAGE_FINAL_COMMISSIONER_REVIEW]).count()
        approved = base_qs.filter(current_stage__name__in=[STAGE_AWAITING_PAYMENT, STAGE_APPROVED]).count()
        rejected = base_qs.filter(current_stage__name=STAGE_REJECTED).count()
        objection = base_qs.filter(current_stage__name=STAGE_COMMISSIONER_OBJECTION).count()
        awaiting_payment = base_qs.filter(current_stage__name=STAGE_AWAITING_PAYMENT).count()
        counts = {
            'applied': pending + approved + rejected,
            'pending':  pending,
            'approved': approved,
            'rejected': rejected,
            'objection': objection,
            'awaiting_payment': awaiting_payment,
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
            'applied':   _serialize(mine.filter(current_stage__name__in=[STAGE_APPLICANT_APPLIED] + OFFICER_PENDING_STAGES)),
            'objection': _serialize(mine.filter(current_stage__name__in=OBJECTION_STAGES)),
            'approved':  _serialize(mine.filter(current_stage__name=STAGE_APPROVED, is_approved=True)),
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
    Wallet debit for Company Collaboration license fee (COMP_COLLAB_FEE).
    When both license fee and security fee are paid (or if renewal), advance workflow from awaiting_payment → final_commissioner_review.
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

    if application.is_license_fee_paid:
        return Response({'detail': 'License fee has already been paid for this application.'}, status=status.HTTP_400_BAD_REQUEST)

    # Fetch fee amount from masters_fixedfee
    try:
        from django.apps import apps
        FixedFee = apps.get_model('core', 'MasterFixedFee')
        fee_obj = FixedFee.objects.filter(fee_code='COMP_COLLAB_FEE', is_active=True).first()
        base_amount = fee_obj.amount if fee_obj else Decimal('25000.00')
    except Exception:
        base_amount = Decimal('25000.00')

    if getattr(application, 'is_renewal', False):
        amount = base_amount
        remarks = f'Company Collaboration fee paid for {application.application_id}'
    else:
        amount = base_amount + Decimal('25000.00')
        remarks = f'Company Collaboration fee (25000) & Company Registration fee (25000) paid for {application.application_id}'

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
            remarks=remarks,
            reference_no=application.application_id,
        )
    except Exception as exc:
        return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    try:
        with transaction.atomic():
            application.is_license_fee_paid = True

            if application.is_paid:
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
            {'detail': f'Payment succeeded but workflow update failed: {str(exc)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    fresh = CompanyCollaboration.objects.get(pk=application.pk)
    return Response({
        'success': True,
        'transaction_id': txn_id,
        'application': CompanyCollaborationSerializer(fresh).data,
    })


# ---------------------------------------------------------------------------
# GET /final-license/<application_id>/
# Returns the data needed to render the FORM D-11 (Collaboration Certificate)
# ---------------------------------------------------------------------------

@api_view(['GET'])
@permission_classes([HasCompanyCollaborationViewPermission])
def final_license_detail(request, application_id):
    from django.core import signing
    from urllib.parse import quote

    raw_id = str(application_id or '').strip()
    token = raw_id
    low = token.lower()
    if low.startswith('val:') or low.startswith('val-') or low.startswith('val '):
        token = token[4:].strip()

    resolved_application_id = raw_id
    validated_via_code = False
    try:
        payload = signing.loads(token, salt='final-license')
    except Exception:
        try:
            payload = signing.loads(token, salt='final-license-collab')
        except Exception:
            payload = None

    if isinstance(payload, dict) and payload.get('source') == 'company_collaboration' and payload.get('applicationId'):
        resolved_application_id = str(payload['applicationId'])
        validated_via_code = True
    else:
        resolved_application_id = raw_id

    # Resolve company collaboration application from license_id or renewal_id
    if resolved_application_id.startswith('RCOL/'):
        from models.transactional.license_renewal_application.models import LicenseApplication as LRA
        lra_app = LRA.objects.filter(application_id=resolved_application_id).first()
        if lra_app and lra_app.old_license_id:
            resolved_application_id = lra_app.old_license_id

    if resolved_application_id.startswith('CC/'):
        from models.masters.license.models import License
        lic = License.objects.filter(license_id=resolved_application_id).first()
        if lic and lic.source_object_id:
            resolved_application_id = lic.source_object_id

    application = get_object_or_404(CompanyCollaboration, application_id=resolved_application_id)

    role_name = request.user.role.name if request.user.role else None
    role = _normalize_role(role_name)
    if role == 'licensee' and application.applicant != request.user:
        return Response({'detail': 'Not found or not authorized.'}, status=status.HTTP_404_NOT_FOUND)

    signed_code = signing.dumps(
        {'applicationId': application.application_id, 'source': 'company_collaboration'},
        salt='final-license',
    )
    validation_url = request.build_absolute_uri(f'/v/{quote(signed_code, safe=":")}/')

    # Resolve the license associated with this company collaboration
    from models.masters.license.models import License
    lic = License.objects.filter(source_object_id=str(application.pk)).first()

    # Build the collaboration registration ID fallback (CCF/<serial>)
    parts = application.application_id.split('/')
    serial_str = parts[-1] if parts else '0001'
    try:
        serial_num = int(serial_str)
    except ValueError:
        serial_num = 1
    collab_reg_id = f'CCF/{serial_num:08d}'

    license_number = collab_reg_id
    valid_from_str = ''
    valid_to_str = ''
    if lic:
        license_number = lic.license_id
        if lic.issue_date:
            valid_from_str = lic.issue_date.strftime('%d/%m/%Y')
        if lic.valid_up_to:
            valid_to_str = lic.valid_up_to.strftime('%d/%m/%Y')

    # Extract transaction ID and date from the PAY workflow transaction
    txn_ref = ''
    txn_date = ''
    security_deposit_ref = ''
    security_deposit_date = ''
    try:
        pay_txn = None
        if lic:
            from models.transactional.license_renewal_application.models import LicenseApplication as LRA
            lra_app = LRA.objects.filter(old_license_id=str(lic.license_id), is_approved=True).order_by('-created_at').first()
            if lra_app:
                from auth.workflow.models import Transaction as WorkflowTransaction
                from django.contrib.contenttypes.models import ContentType
                ct_lra = ContentType.objects.get_for_model(lra_app)
                pay_txn = WorkflowTransaction.objects.filter(
                    content_type=ct_lra,
                    object_id=str(lra_app.pk),
                    action='PAY',
                ).order_by('-created_at').first()

        if not pay_txn:
            from auth.workflow.models import Transaction as WorkflowTransaction
            from django.contrib.contenttypes.models import ContentType
            ct_cc = ContentType.objects.get_for_model(application)
            pay_txn = WorkflowTransaction.objects.filter(
                content_type=ct_cc,
                object_id=str(application.pk),
                action='PAY',
            ).order_by('-created_at').first()

        if pay_txn:
            remarks = str(pay_txn.remarks or '')
            if 'Trans ID:' in remarks:
                txn_ref = remarks.split('Trans ID:')[-1].strip()
            else:
                txn_ref = remarks
            if pay_txn.created_at:
                txn_date = pay_txn.created_at.strftime('%d/%m/%Y')
    except Exception:
        pass

    # Fee amounts — from fee_structure or master fee table
    collab_fee_amount = ''
    security_deposit_amount = ''
    try:
        fee_struct = application.fee_structure or {}
        if isinstance(fee_struct, dict):
            collab_fee = fee_struct.get('collaborationFee') or fee_struct.get('collaboration_fee') or fee_struct.get('collaboration_fees', '')
            sec_dep = fee_struct.get('securityDeposit') or fee_struct.get('security_deposit', '')
            if collab_fee:
                collab_fee_amount = f'{float(collab_fee):.2f}'
            if sec_dep:
                security_deposit_amount = f'{float(sec_dep):.2f}'
    except Exception:
        pass

    # Fallback: load from master BrandOwnerFee if not in fee_structure
    if not collab_fee_amount or not security_deposit_amount:
        try:
            from models.masters.company_collaboration.models import BrandOwnerFee
            fee_obj = BrandOwnerFee.objects.filter(active_status=1).order_by('-from_date').first()
            if fee_obj:
                if not collab_fee_amount:
                    collab_fee_amount = f'{float(fee_obj.collaboration_fees):.2f}'
                if not security_deposit_amount:
                    security_deposit_amount = f'{float(fee_obj.security_deposit):.2f}'
        except Exception:
            pass

    # Fallback to fixed fee constant
    if not collab_fee_amount:
        collab_fee_amount = '25000.00'
    if not security_deposit_amount:
        security_deposit_amount = '0.00'

    # Build brands table rows from selected_brands JSONField (with overview_summary fallback)
    # Frontend stores brands as CompanyCollaborationBrand objects:
    #   { brand_name, brand_code, category, type, kind, selected_sizes: ['750 Ml', '375 Ml'], ... }
    brands_table = []
    try:
        selected_brands = application.selected_brands or []
        # Fallback to overview_summary.selectedBrands if selected_brands is empty
        if not selected_brands:
            summary = application.overview_summary or {}
            if isinstance(summary, dict):
                selected_brands = summary.get('selectedBrands') or summary.get('selected_brands') or []
        if isinstance(selected_brands, list) and selected_brands:
            sl_no = 1
            for brand in selected_brands:
                if not isinstance(brand, dict):
                    continue
                # Handle both camelCase and snake_case field names from the frontend
                brand_name = (
                    brand.get('brand_name') or brand.get('brandName') or
                    brand.get('name') or brand.get('label') or ''
                )
                sizes = brand.get('selected_sizes') or brand.get('selectedSizes') or []
                # Sizes may be a list of strings ('750 Ml') or dicts ({label:'750 Ml', value:750})
                size_labels = []
                for sz in sizes:
                    if isinstance(sz, str):
                        size_labels.append(sz)
                    elif isinstance(sz, dict):
                        size_labels.append(sz.get('label') or sz.get('value') or str(sz))
                if size_labels:
                    for size in size_labels:
                        brands_table.append({
                            'sl_no': sl_no,
                            'brand_name': brand_name,
                            'pack_size': str(size),
                        })
                        sl_no += 1
                else:
                    brands_table.append({
                        'sl_no': sl_no,
                        'brand_name': brand_name,
                        'pack_size': '-',
                    })
                    sl_no += 1
    except Exception as brand_err:
        import logging as _logging
        _logging.getLogger(__name__).error(f"Error building brands_table: {brand_err}")
        brands_table = []

    response_payload = {
        'applicationId': application.application_id,
        'certificateType': 'company-collaboration',
        'licenseNumber': license_number,
        'licenseTitle': 'FORM D-11 (See Rule 33)',
        'validationCode': signed_code,
        'validationPdfUrl': validation_url,
        'validatedViaCode': validated_via_code,
        'validFrom': valid_from_str,
        'validTo': valid_to_str,
        'print_count': 0,
        'is_print_fee_paid': True,
        'terms': [],

        # Brand owner (the collaborating company)
        'brandOwnerName': application.brand_owner_name or application.brand_owner or '',
        'brandOwnerCode': application.brand_owner_code or '',

        # Licensee / bottler (factory premises)
        'licenseeName': application.licensee_name or '',
        'licenseeAddress': application.licensee_address or '',
        'licenseNumber_bottler': application.license_number or '',

        # Financial year
        'applicationYear': application.application_year or application.financial_year or '',
        'financialYear': application.financial_year or '',

        # Fees and transactions
        'collaborationFee': collab_fee_amount,
        'securityDeposit': security_deposit_amount,
        'transactionRef': txn_ref,
        'transactionDate': txn_date,
        'securityDepositRef': security_deposit_ref,
        'securityDepositDate': security_deposit_date,
        'generatedOn': application.updated_at.strftime('%d/%m/%Y') if application.updated_at else '',
        'applicationDateTime': application.created_at.strftime('%d/%m/%Y') if application.created_at else '',

        # Brands
        'brandsTable': brands_table,

        # QR
        'qrCodeDataUrl': _make_collab_qr_data_url(validation_url),
    }

    return Response(response_payload, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([HasCompanyCollaborationViewPermission])
def final_license_qr_code(request, application_id):
    import base64
    from django.core import signing
    from django.http import HttpResponse
    from urllib.parse import quote

    application = get_object_or_404(CompanyCollaboration, application_id=application_id)

    role_name = request.user.role.name if request.user.role else None
    role = _normalize_role(role_name)
    if role == 'licensee' and application.applicant != request.user:
        return Response({'detail': 'Not found or not authorized.'}, status=status.HTTP_404_NOT_FOUND)

    signed_code = signing.dumps(
        {'applicationId': application.application_id, 'source': 'company_collaboration'},
        salt='final-license-collab',
    )
    validation_url = request.build_absolute_uri(f'/v/{quote(signed_code, safe=":")}/collab/')
    data_url = _make_collab_qr_data_url(validation_url)
    b64 = data_url.split(',', 1)[1] if ',' in data_url else ''
    return HttpResponse(base64.b64decode(b64), content_type='image/png')


def _make_collab_qr_data_url(payload: str) -> str:
    import base64
    from io import BytesIO
    from PIL import Image
    from utils.qrcodegen import QrCode

    qr = QrCode.encode_text(str(payload or ''), QrCode.Ecc.MEDIUM)
    size = qr.get_size()
    border = 2
    scale = 4
    img_size = (size + border * 2) * scale
    img = Image.new('RGB', (img_size, img_size), 'white')
    pixels = img.load()
    for y in range(size):
        for x in range(size):
            if qr.get_module(x, y):
                for dy in range(scale):
                    for dx in range(scale):
                        pixels[(x + border) * scale + dx, (y + border) * scale + dy] = (0, 0, 0)
    buf = BytesIO()
    img.save(buf, format='PNG')
    return f"data:image/png;base64,{base64.b64encode(buf.getvalue()).decode('ascii')}"

