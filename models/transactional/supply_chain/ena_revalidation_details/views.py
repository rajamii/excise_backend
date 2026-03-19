from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.db import transaction, models
from django.utils import timezone
from decimal import Decimal
import logging
from .models import EnaRevalidationDetail
from .serializers import EnaRevalidationDetailSerializer
from models.transactional.supply_chain.ena_requisition_details.models import EnaRequisitionDetail
from auth.workflow.constants import WORKFLOW_IDS
from models.transactional.supply_chain.access_control import (
    has_workflow_access,
    scope_by_profile_or_workflow,
    transition_matches,
)
# from models.masters.supply_chain.status_master.models import StatusMaster, WorkflowRule # Removed

logger = logging.getLogger(__name__)

class EnaRevalidationDetailViewSet(viewsets.ModelViewSet):
    queryset = EnaRevalidationDetail.objects.all().order_by('-created_at')
    serializer_class = EnaRevalidationDetailSerializer
    permission_classes = [IsAuthenticated]

    REVALIDATION_FEE_AMOUNT = Decimal('1000.00')

    def _expand_license_aliases(self, license_id: str):
        normalized = str(license_id or '').strip()
        if not normalized:
            return []

        candidates = [normalized]
        if normalized.startswith('NLI/'):
            candidates.append(f"NA/{normalized[4:]}")
        if normalized.startswith('NA/'):
            candidates.append(f"NLI/{normalized[3:]}")

        seen = set()
        ordered = []
        for value in candidates:
            if value and value not in seen:
                seen.add(value)
                ordered.append(value)
        return ordered

    def _resolve_wallet_license_candidates(self, revalidation, user):
        candidates = []

        req_license = str(getattr(revalidation, 'licensee_id', '') or '').strip()
        candidates.extend(self._expand_license_aliases(req_license))

        profile_license = ''
        if hasattr(user, 'supply_chain_profile'):
            profile_license = str(getattr(user.supply_chain_profile, 'licensee_id', '') or '').strip()
        candidates.extend(self._expand_license_aliases(profile_license))

        try:
            from models.masters.license.models import License
            active_licenses = License.objects.filter(
                applicant=user,
                source_type='new_license_application',
                is_active=True
            ).order_by('-issue_date')

            for cid in list(candidates):
                hit = active_licenses.filter(
                    models.Q(license_id=cid) | models.Q(source_object_id=cid)
                ).first()
                if hit and hit.license_id:
                    candidates.extend(self._expand_license_aliases(str(hit.license_id)))

            latest = active_licenses.first()
            if latest and latest.license_id:
                candidates.extend(self._expand_license_aliases(str(latest.license_id)))
        except Exception:
            pass

        seen = set()
        ordered = []
        for cid in candidates:
            if cid and cid not in seen:
                seen.add(cid)
                ordered.append(cid)
        return ordered

    def _debit_wallet_for_revalidation_submission(self, revalidation, user):
        from models.transactional.payment.models import WalletBalance, WalletTransaction

        amount = self.REVALIDATION_FEE_AMOUNT
        if amount <= 0:
            return {'debited': False, 'reason': 'zero_amount'}

        reference_no = str(getattr(revalidation, 'our_ref_no', '') or f"REV-{revalidation.pk}")
        transaction_id = f"REV-{revalidation.pk}-PAYMENT"

        already_debited = WalletTransaction.objects.filter(
            transaction_id=transaction_id,
            source_module='ena_revalidation',
            entry_type='DR'
        ).exists()
        if already_debited:
            return {'debited': False, 'reason': 'already_debited'}

        candidates = self._resolve_wallet_license_candidates(revalidation, user)
        if not candidates:
            raise ValueError("Unable to resolve licensee_id for wallet deduction.")

        wallet = None
        resolved_licensee_id = ''

        for cid in candidates:
            wallet = (
                WalletBalance.objects.select_for_update()
                .filter(licensee_id=cid, wallet_type__iexact='excise')
                .order_by('wallet_balance_id')
                .first()
            )
            if wallet:
                resolved_licensee_id = cid
                break

        if not wallet:
            for cid in candidates:
                wallet = (
                    WalletBalance.objects.select_for_update()
                    .filter(licensee_id=cid, wallet_type__iexact='brewery')
                    .order_by('wallet_balance_id')
                    .first()
                )
                if wallet:
                    resolved_licensee_id = cid
                    break

        if not wallet:
            raise ValueError(
                f"Wallet not found for licensee_id. Tried: {', '.join(candidates)}"
            )

        current_balance = Decimal(str(wallet.current_balance or 0))
        if current_balance < amount:
            raise ValueError(
                f"Insufficient wallet balance. Available: {current_balance}, Required: {amount}"
            )

        now_ts = timezone.now()
        after = current_balance - amount
        wallet.current_balance = after
        wallet.total_debit = Decimal(str(wallet.total_debit or 0)) + amount
        wallet.last_updated_at = now_ts
        wallet.save(update_fields=['current_balance', 'total_debit', 'last_updated_at'])

        WalletTransaction.objects.create(
            wallet_balance=wallet,
            transaction_id=transaction_id,
            licensee_id=resolved_licensee_id,
            licensee_name=wallet.licensee_name,
            user_id=str(getattr(user, 'username', '') or wallet.user_id or ''),
            module_type=wallet.module_type,
            wallet_type=wallet.wallet_type,
            head_of_account=wallet.head_of_account,
            entry_type='DR',
            transaction_type='debit',
            amount=amount,
            balance_before=current_balance,
            balance_after=after,
            reference_no=reference_no,
            source_module='ena_revalidation',
            payment_status='success',
            remarks='Revalidation submission fee debit',
            created_at=now_ts,
        )

        return {
            'debited': True,
            'licensee_id': resolved_licensee_id,
            'wallet_type': wallet.wallet_type,
            'amount': str(amount)
        }

    def get_queryset(self):
        queryset = EnaRevalidationDetail.objects.all().order_by('-created_at')
        return scope_by_profile_or_workflow(
            self.request.user,
            queryset,
            WORKFLOW_IDS['ENA_REVALIDATION'],
            licensee_field='licensee_id'
        )

    def get_serializer_context(self):   
        """Override to ensure request context is passed to serializer"""
        context = super().get_serializer_context()
        context['request'] = self.request
        return context

    @action(detail=False, methods=['post'], url_path='from-requisition')
    def create_from_requisition(self, request):
        """
        Create (or reuse) a revalidation record from an approved requisition.
        Accepts requisition_id or requisition_ref_no in the request payload.
        """
        requisition_id = request.data.get('requisition_id') or request.data.get('id') or request.data.get('requisitionId')
        requisition_ref = (
            request.data.get('requisition_ref_no')
            or request.data.get('ref')
            or request.data.get('reference_no')
            or request.data.get('referenceNo')
        )

        requisition = None
        if requisition_id:
            requisition = EnaRequisitionDetail.objects.filter(id=requisition_id).first()
        if requisition is None and requisition_ref:
            requisition = EnaRequisitionDetail.objects.filter(our_ref_no=requisition_ref).first()

        if requisition is None:
            return Response(
                {'error': 'Requisition not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        existing = None
        details_token = str(getattr(requisition, 'details_permits_number', '') or '').strip()
        license_token = str(getattr(requisition, 'licensee_id', '') or '').strip()

        if license_token and details_token:
            existing = EnaRevalidationDetail.objects.filter(
                licensee_id=license_token,
                details_permits_number=details_token,
            ).order_by('-created_at').first()

        if existing is None and details_token:
            existing = EnaRevalidationDetail.objects.filter(
                details_permits_number=details_token
            ).order_by('-created_at').first()

        if existing is None and license_token:
            existing = EnaRevalidationDetail.objects.filter(
                licensee_id=license_token
            ).order_by('-created_at').first()

        if existing:
            serializer = self.get_serializer(existing)
            return Response({
                'status': 'success',
                'message': 'Revalidation already exists for this requisition',
                'data': serializer.data
            }, status=status.HTTP_200_OK)

        now = timezone.now()
        payload = {
            'requisition_date': requisition.requisition_date,
            'grain_ena_number': requisition.grain_ena_number,
            'bulk_spirit_type': requisition.bulk_spirit_type or '',
            'strength': requisition.strength or '',
            'lifted_from': requisition.lifted_from or '',
            'via_route': requisition.via_route or '',
            'total_bl': requisition.totalbl or 0,
            'br_amount': requisition.totalbl or 0,
            'requisiton_number_of_permits': requisition.requisiton_number_of_permits or 0,
            'branch_name': requisition.lifted_from_distillery_name or requisition.check_post_name or '',
            'branch_address': '',
            'branch_purpose': requisition.branch_purpose or requisition.purpose_name or '',
            'govt_officer': '',
            'state': requisition.state or '',
            'revalidation_date': now,
            'status': 'IMPORT PERMIT EXTENDS 45 DAYS INVALID',
            'status_code': 'RV_00',
            'revalidation_br_amount': str(self.REVALIDATION_FEE_AMOUNT),
            'details_permits_number': requisition.details_permits_number or '',
            'distillery_name': requisition.lifted_from_distillery_name or requisition.lifted_from or '',
        }

        if license_token:
            payload['licensee_id'] = license_token

        serializer = self.get_serializer(data=payload)
        serializer.is_valid(raise_exception=True)
        revalidation = serializer.save()

        response_payload = {
            'status': 'success',
            'message': 'Revalidation created from requisition',
            'data': self.get_serializer(revalidation).data
        }
        return Response(response_payload, status=status.HTTP_201_CREATED)

    # Note: allowed_actions is now handled by SerializerMethodField in serializer
    # Following the same pattern as requisition - no custom list() override needed

    @action(detail=True, methods=['post'])
    def submit_revalidation(self, request, pk=None):
        """Submit a revalidation request and set initial status"""
        try:
            revalidation = self.get_object()
            
            # Use Workflow Logic for initialization
            from auth.workflow.models import Workflow, WorkflowStage
            
            # HARDCODED INITIAL STATE (StatusMaster module is deprecated/removed)
            status_name = 'ForwardedRevalidationToCommissioner'
            status_code = 'RV_02' # Assuming 01 was Pending, 02 might be Forwarded - this is just a string code
            
            wallet_result = None
            with transaction.atomic():
                wallet_result = self._debit_wallet_for_revalidation_submission(
                    revalidation=revalidation,
                    user=request.user
                )

                # Bind to Workflow
                try:
                    workflow = Workflow.objects.get(id=WORKFLOW_IDS['ENA_REVALIDATION'])
                    stage = (
                        WorkflowStage.objects.filter(workflow=workflow, name=status_name).first()
                        or WorkflowStage.objects.filter(
                            workflow=workflow,
                            name__icontains='forward'
                        ).filter(name__icontains='commissioner').first()
                        or WorkflowStage.objects.filter(workflow=workflow, is_initial=True).first()
                        or WorkflowStage.objects.filter(workflow=workflow).order_by('id').first()
                    )

                    if stage:
                        revalidation.workflow = workflow
                        revalidation.current_stage = stage
                        revalidation.status = stage.name
                    else:
                        revalidation.status = status_name
                except Exception as e:
                    # Log warning but don't fail if workflow setup incomplete (though it should be complete)
                    logger.warning("Workflow binding failed for revalidation=%s", revalidation.id, exc_info=True)
                    revalidation.status = status_name

                revalidation.status_code = status_code

                revalidation.save()
            
            serializer = self.get_serializer(revalidation)
            response_payload = {
                'status': 'success',
                'message': f'Revalidation submitted with status: {status_name}',
                'data': serializer.data
            }
            if wallet_result is not None:
                response_payload['wallet_deduction'] = wallet_result
            return Response(response_payload, status=status.HTTP_200_OK)
            
        except Exception as e:
            return Response({
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=['post'])
    def perform_action(self, request, pk=None):
        """Perform an action (APPROVE/REJECT) on a revalidation using WorkflowService"""
        try:
            revalidation = self.get_object()
            action_type = request.data.get('action') # APPROVE / REJECT
            remarks = request.data.get('remarks', f"Action {action_type} performed")
            
            if not action_type:
                 return Response({'error': 'Action is required'}, status=status.HTTP_400_BAD_REQUEST)

            # Determine Role
            user = request.user
            if not has_workflow_access(user, WORKFLOW_IDS['ENA_REVALIDATION']) and not hasattr(user, 'supply_chain_profile'):
                return Response({'error': 'Unauthorized role for this workflow'}, status=status.HTTP_403_FORBIDDEN)

            # Use Workflow Service
            from auth.workflow.services import WorkflowService
            
            # Ensure workflow/stage is set (migration fallback)
            if not revalidation.workflow or not revalidation.current_stage:
                 # Try to recover state from status_name
                 from auth.workflow.models import Workflow, WorkflowStage
                 try:
                     wf = Workflow.objects.get(id=WORKFLOW_IDS['ENA_REVALIDATION'])
                     stage = WorkflowStage.objects.get(workflow=wf, name=revalidation.status)
                     revalidation.workflow = wf
                     revalidation.current_stage = stage
                     revalidation.save()
                 except Exception as e:
                     return Response({'error': f'Workflow state error: {e}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
            # Find Transition
            transitions = WorkflowService.get_next_stages(revalidation)
            target_transition = None
            
            for t in transitions:
                if transition_matches(t, user, action_type):
                    target_transition = t
                    break
            
            if not target_transition:
                return Response({
                    'error': f'Invalid action {action_type} at stage {revalidation.current_stage.name}'
                }, status=status.HTTP_400_BAD_REQUEST)

            # Advance Stage
            try:
                WorkflowService.advance_stage(
                    application=revalidation,
                    user=user,
                    target_stage=target_transition.to_stage,
                    context={'action': action_type},
                    remarks=remarks
                )
                
                # Update status explicitly
                revalidation.status = target_transition.to_stage.name
                # revalidation.status_code = ... # Removed dependency
                revalidation.save()

                serializer = self.get_serializer(revalidation)
                return Response({
                    'status': 'success',
                    'message': f'Action {action_type} performed successfully. New Status: {revalidation.status}',
                    'data': serializer.data
                }, status=status.HTTP_200_OK)

            except ValueError as e:
                return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
            except PermissionError as e:
                return Response({'error': str(e)}, status=status.HTTP_403_FORBIDDEN)
            
        except EnaRevalidationDetail.DoesNotExist:
            return Response({
                'error': 'Revalidation not found'
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.exception("Unhandled error during revalidation action")
            return Response({
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
