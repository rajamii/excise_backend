import re
from decimal import Decimal
from django.db import models, transaction
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.exceptions import ValidationError, PermissionDenied

from .models import EnaBulkSpiritUsage
from .serializers import EnaBulkSpiritUsageSerializer
from auth.workflow.constants import WORKFLOW_IDS
from auth.workflow.models import Workflow, WorkflowStage
from auth.workflow.services import WorkflowService
from models.transactional.supply_chain.ena_requisition_details.models import (
    EnaRequisitionDetail,
    RequisitionBulkLiterDetail
)
from models.masters.license.models import License
from models.masters.supply_chain.bulk_spirit.models import BulkSpiritType


def _expand_license_aliases(value: str) -> list[str]:
    token = str(value or '').strip()
    if not token:
        return []
    aliases = [token]
    if token.startswith('NLI/'):
        aliases.append(f'NA/{token[4:]}')
    elif token.startswith('NA/'):
        aliases.append(f'NLI/{token[3:]}')
    return aliases


def _resolve_user_licensee_candidates(user) -> list[str]:
    if not user or not user.is_authenticated:
        return []
    
    candidates = set()
    # 1. From active licenses
    qs = License.objects.filter(applicant=user, is_active=True).values_list('license_id', flat=True)
    for lic_id in qs:
        for alias in _expand_license_aliases(lic_id):
            candidates.add(alias)

    # 2. From manufacturing units if any
    if hasattr(user, 'manufacturing_units'):
        unit_ids = user.manufacturing_units.exclude(licensee_id__isnull=True).exclude(licensee_id='').values_list('licensee_id', flat=True)
        for u_id in unit_ids:
            for alias in _expand_license_aliases(u_id):
                candidates.add(alias)

    # 3. From OIC assignment if OIC user
    if hasattr(user, 'oic_assignment'):
        assignment = getattr(user, 'oic_assignment')
        mapped_values = [
            getattr(assignment, 'licensee_id', ''),
            getattr(getattr(assignment, 'license', None), 'license_id', ''),
            getattr(getattr(assignment, 'approved_application', None), 'application_id', ''),
        ]
        for val in mapped_values:
            for alias in _expand_license_aliases(val):
                candidates.add(alias)

    return list(candidates)


def _get_inventory_summary_for_licensee(licensee_candidates: list[str], specific_spirit_type: str = None) -> dict:
    # Calculates the arrived BL, approved used BL, pending used BL, and net available BL.
    if not licensee_candidates:
        return {'by_type': {}, 'total_arrived': Decimal('0'), 'total_used': Decimal('0'), 'total_pending': Decimal('0'), 'total_available': Decimal('0')}

    # 1. Query approved tanker arrivals from RequisitionBulkLiterDetail
    approved_arrivals = RequisitionBulkLiterDetail.objects.filter(
        approval_status=RequisitionBulkLiterDetail.ApprovalStatus.APPROVED,
        licensee_id__in=licensee_candidates
    ).select_related('requisition')

    # If no arrivals directly by licensee_id, try by requisitions belonging to these licensee IDs
    if not approved_arrivals.exists():
        req_ids = EnaRequisitionDetail.objects.filter(licensee_id__in=licensee_candidates).values_list('id', flat=True)
        approved_arrivals = RequisitionBulkLiterDetail.objects.filter(
            approval_status=RequisitionBulkLiterDetail.ApprovalStatus.APPROVED,
            requisition_id__in=req_ids
        ).select_related('requisition')

    by_type = {}

    for arrival in approved_arrivals:
        req = getattr(arrival, 'requisition', None)
        spirit_type = (getattr(req, 'bulk_spirit_type', '') or 'General Bulk Spirit').strip()
        if not spirit_type:
            spirit_type = 'General Bulk Spirit'

        if specific_spirit_type and spirit_type.lower() != specific_spirit_type.lower():
            continue

        if spirit_type not in by_type:
            by_type[spirit_type] = {
                'spirit_type': spirit_type,
                'arrived_bl': Decimal('0'),
                'approved_usage_bl': Decimal('0'),
                'pending_usage_bl': Decimal('0'),
                'available_bl': Decimal('0')
            }
        
        arrived_amount = Decimal(str(arrival.total_bulk_liter or 0))
        by_type[spirit_type]['arrived_bl'] += arrived_amount

    # 2. Query usage records
    usage_records = EnaBulkSpiritUsage.objects.filter(
        licensee_id__in=licensee_candidates
    )

    for usage in usage_records:
        spirit_type = (usage.bulk_spirit_type or 'General Bulk Spirit').strip()
        if specific_spirit_type and spirit_type.lower() != specific_spirit_type.lower():
            continue

        if spirit_type not in by_type:
            by_type[spirit_type] = {
                'spirit_type': spirit_type,
                'arrived_bl': Decimal('0'),
                'approved_usage_bl': Decimal('0'),
                'pending_usage_bl': Decimal('0'),
                'available_bl': Decimal('0')
            }

        usage_amount = Decimal(str(usage.quantity or 0))
        st = str(usage.status or '').strip().lower()
        if st in ['approved', 'completed']:
            by_type[spirit_type]['approved_usage_bl'] += usage_amount
        elif st in ['pending', 'pending oic approval', 'pending approval']:
            by_type[spirit_type]['pending_usage_bl'] += usage_amount

    # 3. Calculate net available for each
    total_arrived = Decimal('0')
    total_used = Decimal('0')
    total_pending = Decimal('0')
    total_available = Decimal('0')

    for stype, data in by_type.items():
        net = data['arrived_bl'] - (data['approved_usage_bl'] + data['pending_usage_bl'])
        data['available_bl'] = max(Decimal('0'), net)
        total_arrived += data['arrived_bl']
        total_used += data['approved_usage_bl']
        total_pending += data['pending_usage_bl']
        total_available += data['available_bl']

    return {
        'by_type': by_type,
        'total_arrived': total_arrived,
        'total_used': total_used,
        'total_pending': total_pending,
        'total_available': total_available
    }


def _get_next_usage_ref_number() -> str:
    existing_refs = EnaBulkSpiritUsage.objects.values_list('reference_no', flat=True)
    numbers = []
    pattern = r'BSU/(\d+)/EXCISE'
    for ref in existing_refs:
        m = re.match(pattern, str(ref or ''))
        if m:
            try:
                numbers.append(int(m.group(1)))
            except ValueError:
                pass
    next_num = (max(numbers) + 1) if numbers else 1
    return f'BSU/{next_num:02d}/EXCISE'


class EnaBulkSpiritUsageListCreateAPIView(generics.ListCreateAPIView):
    serializer_class = EnaBulkSpiritUsageSerializer

    def get_queryset(self):
        user = self.request.user
        role_name = str(getattr(getattr(user, 'role', None), 'name', '') or '').lower()
        is_admin_or_comm = any(k in role_name for k in ['admin', 'commissioner', 'jointcommissioner', 'super'])

        if is_admin_or_comm:
            return EnaBulkSpiritUsage.objects.all().select_related('applicant', 'current_stage')

        candidates = _resolve_user_licensee_candidates(user)
        is_oic = 'officerincharge' in role_name or 'oic' in role_name or hasattr(user, 'oic_assignment')

        if is_oic:
            if candidates:
                return EnaBulkSpiritUsage.objects.filter(licensee_id__in=candidates).select_related('applicant', 'current_stage')
            return EnaBulkSpiritUsage.objects.all().select_related('applicant', 'current_stage')

        # Licensee
        if candidates:
            return EnaBulkSpiritUsage.objects.filter(
                models.Q(applicant=user) | models.Q(licensee_id__in=candidates)
            ).select_related('applicant', 'current_stage')

        return EnaBulkSpiritUsage.objects.filter(applicant=user).select_related('applicant', 'current_stage')

    def perform_create(self, serializer):
        user = self.request.user
        candidates = _resolve_user_licensee_candidates(user)
        licensee_id = self.request.data.get('licensee_id') or (candidates[0] if candidates else '')
        spirit_type = str(self.request.data.get('bulk_spirit_type') or '').strip()
        
        try:
            quantity = Decimal(str(self.request.data.get('quantity') or 0))
        except Exception:
            raise ValidationError({'quantity': 'Valid quantity in Bulk Liters is required.'})

        if quantity <= 0:
            raise ValidationError({'quantity': 'Quantity must be greater than 0 BL.'})

        if not spirit_type:
            raise ValidationError({'bulk_spirit_type': 'Bulk Spirit Type is required.'})

        # Check for existing pending request
        pending_qs = EnaBulkSpiritUsage.objects.filter(
            models.Q(status__iexact='Pending') | models.Q(status__icontains='pending')
        )
        if candidates:
            pending_qs = pending_qs.filter(models.Q(applicant=user) | models.Q(licensee_id__in=candidates))
        else:
            pending_qs = pending_qs.filter(applicant=user)

        pending_usage = pending_qs.first()
        if pending_usage:
            raise ValidationError({
                'non_field_errors': [
                    f"You can submit the next Bulk Spirit Usage request only after ref no. {pending_usage.reference_no} is verified (approved or rejected) by the Officer-In-Charge (OIC)."
                ]
            })

        # Check inventory
        summary = _get_inventory_summary_for_licensee(candidates, specific_spirit_type=spirit_type)
        type_summary = summary['by_type'].get(spirit_type)
        available_bl = type_summary['available_bl'] if type_summary else Decimal('0')

        if quantity > available_bl:
            raise ValidationError({
                'quantity': f'Insufficient bulk spirit inventory. Available: {available_bl:,.2f} BL, Requested: {quantity:,.2f} BL.'
            })

        # Resolve establishment / distillery name
        distillery_name = ''
        latest_req = EnaRequisitionDetail.objects.filter(licensee_id__in=candidates).order_by('-id').first()
        if latest_req:
            distillery_name = latest_req.lifted_from_distillery_name or ''
        if not distillery_name:
            lic = License.objects.filter(license_id__in=candidates).first()
            if lic:
                distillery_name = getattr(lic, 'establishment_name', '') or ''
        if not distillery_name:
            distillery_name = f'{user.first_name} {user.last_name}'.strip() or user.username

        # Get or setup workflow
        workflow_id = WORKFLOW_IDS.get('ENA_BULK_SPIRIT_USAGE', 18)
        workflow = Workflow.objects.filter(id=workflow_id).first()
        initial_stage = WorkflowStage.objects.filter(workflow=workflow, is_initial=True).first() if workflow else None

        ref_no = _get_next_usage_ref_number()

        serializer.save(
            reference_no=ref_no,
            licensee_id=licensee_id,
            distillery_name=distillery_name,
            applicant=user,
            bulk_spirit_type=spirit_type,
            quantity=quantity,
            status='Pending',
            status_code='BSU_00',
            workflow=workflow,
            current_stage=initial_stage
        )


class EnaBulkSpiritUsageInventorySummaryAPIView(APIView):
    def get(self, request):
        user = request.user
        candidates = _resolve_user_licensee_candidates(user)
        
        # Also include any known types from BulkSpiritType master
        master_types = list(BulkSpiritType.objects.values_list('bulk_spirit_kind_type', flat=True).distinct())

        summary = _get_inventory_summary_for_licensee(candidates)
        by_type = summary['by_type']

        # Ensure all types found in arrivals or masters are present in by_type
        for m_type in master_types:
            m_clean = str(m_type or '').strip()
            if m_clean and m_clean not in by_type:
                found = False
                for existing in by_type.keys():
                    if existing.lower() == m_clean.lower():
                        found = True
                        break
                if not found:
                    by_type[m_clean] = {
                        'spirit_type': m_clean,
                        'arrived_bl': Decimal('0'),
                        'approved_usage_bl': Decimal('0'),
                        'pending_usage_bl': Decimal('0'),
                        'available_bl': Decimal('0')
                    }

        result_list = []
        for stype, data in sorted(by_type.items(), key=lambda x: str(x[0])):
            result_list.append({
                'bulk_spirit_type': data['spirit_type'],
                'total_arrived_bl': float(data['arrived_bl']),
                'total_approved_usage_bl': float(data['approved_usage_bl']),
                'total_pending_usage_bl': float(data['pending_usage_bl']),
                'available_bl': float(data['available_bl'])
            })

        return Response({
            'status': 'success',
            'data': result_list,
            'total_arrived_bl': float(summary['total_arrived']),
            'total_used_bl': float(summary['total_used']),
            'total_pending_bl': float(summary['total_pending']),
            'total_available_bl': float(summary['total_available'])
        }, status=status.HTTP_200_OK)


class EnaBulkSpiritUsagePerformActionAPIView(APIView):
    def post(self, request, pk):
        try:
            usage = EnaBulkSpiritUsage.objects.get(pk=pk)
        except EnaBulkSpiritUsage.DoesNotExist:
            return Response({'status': 'error', 'message': 'Usage request not found.'}, status=status.HTTP_404_NOT_FOUND)

        action = str(request.data.get('action') or '').strip().upper()
        remarks = str(request.data.get('remarks') or request.data.get('reason') or '').strip()

        if action not in ['APPROVE', 'REJECT']:
            return Response({'status': 'error', 'message': 'Valid action (APPROVE or REJECT) is required.'}, status=status.HTTP_400_BAD_REQUEST)

        if action == 'REJECT' and not remarks:
            return Response({'status': 'error', 'message': 'Rejection remarks/reason is required.'}, status=status.HTTP_400_BAD_REQUEST)

        user = request.user
        role_name = str(getattr(getattr(user, 'role', None), 'name', '') or '').lower()
        is_oic = 'officerincharge' in role_name or 'oic' in role_name or hasattr(user, 'oic_assignment')
        is_admin = any(k in role_name for k in ['admin', 'commissioner', 'jointcommissioner'])

        if not (is_oic or is_admin):
            return Response({'status': 'error', 'message': 'Only Officer-In-Charge can approve or reject usage requests.'}, status=status.HTTP_403_FORBIDDEN)

        workflow_id = WORKFLOW_IDS.get('ENA_BULK_SPIRIT_USAGE', 18)
        workflow = Workflow.objects.filter(id=workflow_id).first()

        target_stage_name = 'Approved' if action == 'APPROVE' else 'Rejected'
        target_stage = None
        if workflow:
            target_stage = WorkflowStage.objects.filter(workflow=workflow, name__iexact=target_stage_name).first()

        now = timezone.now()
        with transaction.atomic():
            if action == 'APPROVE':
                usage.status = 'Approved'
                usage.status_code = 'BSU_01'
                usage.rejection_reason = ''
            else:
                usage.status = 'Rejected'
                usage.status_code = 'BSU_02'
                usage.rejection_reason = remarks

            if target_stage:
                usage.current_stage = target_stage

            reviewer_name = f'{user.first_name} {user.last_name}'.strip() or user.username
            usage.reviewed_by = reviewer_name
            usage.reviewed_at = now
            usage.save()

        serializer = EnaBulkSpiritUsageSerializer(usage, context={'request': request})
        return Response({
            'status': 'success',
            'message': f'Bulk Spirit Usage request {action.lower()}d successfully.',
            'data': serializer.data
        }, status=status.HTTP_200_OK)
