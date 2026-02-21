from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.utils import timezone
from django.db import transaction, models
from decimal import Decimal
import re
from .models import EnaCancellationDetail
from .serializers import EnaCancellationDetailSerializer, CancellationCreateSerializer
from auth.workflow.constants import WORKFLOW_IDS
from models.transactional.supply_chain.access_control import (
    has_workflow_access,
    scope_by_profile_or_workflow,
    transition_matches,
)

class EnaCancellationDetailViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows ENA cancellation details to be viewed or edited.
    """
    queryset = EnaCancellationDetail.objects.all().order_by('-created_at')
    serializer_class = EnaCancellationDetailSerializer
    permission_classes = [permissions.IsAuthenticated]
    CANCELLATION_FEE_AMOUNT = Decimal('1000.00')

    def _generate_cancellation_ref(self) -> str:
        existing_refs = EnaCancellationDetail.objects.values_list('our_ref_no', flat=True)
        pattern = r'CAN/(\d+)/EXCISE'
        numbers = []

        for ref in existing_refs:
            match = re.match(pattern, str(ref or ''))
            if match:
                numbers.append(int(match.group(1)))

        next_number = (max(numbers) + 1) if numbers else 1
        return f"CAN/{next_number:02d}/EXCISE"

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

    def _resolve_wallet_license_candidates(self, cancellation, user):
        candidates = []

        cancellation_license_id = str(getattr(cancellation, 'license_id', '') or '').strip()
        candidates.extend(self._expand_license_aliases(cancellation_license_id))

        req_licensee = str(getattr(cancellation, 'licensee_id', '') or '').strip()
        candidates.extend(self._expand_license_aliases(req_licensee))

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

    def _debit_wallet_for_cancellation_submission(self, cancellation, user, amount):
        from models.transactional.payment.models import WalletBalance, WalletTransaction

        amount_decimal = Decimal(str(amount or 0))
        if amount_decimal <= 0:
            return {'debited': False, 'reason': 'zero_amount'}

        reference_no = str(getattr(cancellation, 'our_ref_no', '') or f"CAN-{cancellation.pk}")
        transaction_id = f"CAN-{cancellation.pk}-PAYMENT"

        already_debited = WalletTransaction.objects.filter(
            transaction_id=transaction_id,
            source_module='ena_cancellation',
            entry_type='DR'
        ).exists()
        if already_debited:
            return {'debited': False, 'reason': 'already_debited'}

        candidates = self._resolve_wallet_license_candidates(cancellation, user)
        if not candidates:
            raise ValueError("Unable to resolve license id for wallet deduction.")

        wallet = None
        resolved_license_id = ''

        for cid in candidates:
            wallet = (
                WalletBalance.objects.select_for_update()
                .filter(licensee_id=cid, wallet_type__iexact='excise')
                .order_by('wallet_balance_id')
                .first()
            )
            if wallet:
                resolved_license_id = cid
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
                    resolved_license_id = cid
                    break

        if not wallet:
            raise ValueError(
                f"Wallet not found for license id. Tried: {', '.join(candidates)}"
            )

        current_balance = Decimal(str(wallet.current_balance or 0))
        if current_balance < amount_decimal:
            raise ValueError(
                f"Insufficient wallet balance. Available: {current_balance}, Required: {amount_decimal}"
            )

        now_ts = timezone.now()
        after = current_balance - amount_decimal
        wallet.current_balance = after
        wallet.total_debit = Decimal(str(wallet.total_debit or 0)) + amount_decimal
        wallet.last_updated_at = now_ts
        wallet.save(update_fields=['current_balance', 'total_debit', 'last_updated_at'])

        WalletTransaction.objects.create(
            wallet_balance=wallet,
            transaction_id=transaction_id,
            licensee_id=resolved_license_id,
            licensee_name=wallet.licensee_name,
            user_id=str(getattr(user, 'username', '') or wallet.user_id or ''),
            module_type=wallet.module_type,
            wallet_type=wallet.wallet_type,
            head_of_account=wallet.head_of_account,
            entry_type='DR',
            transaction_type='debit',
            amount=amount_decimal,
            balance_before=current_balance,
            balance_after=after,
            reference_no=reference_no,
            source_module='ena_cancellation',
            payment_status='success',
            remarks='Cancellation submission fee debit',
            created_at=now_ts,
        )

        return {
            'debited': True,
            'license_id': resolved_license_id,
            'wallet_type': wallet.wallet_type,
            'amount': str(amount_decimal)
        }

    def get_queryset(self):
        """
        Optionally restricts the returned cancellations by filtering against
        query parameters in the URL and the current user's licensee profile.
        """
        queryset = EnaCancellationDetail.objects.all().order_by('-created_at')
        queryset = scope_by_profile_or_workflow(
            self.request.user,
            queryset,
            WORKFLOW_IDS['ENA_CANCELLATION'],
            licensee_field='licensee_id'
        )

        our_ref_no = self.request.query_params.get('our_ref_no', None)
        status_param = self.request.query_params.get('status', None)
        
        if our_ref_no is not None:
            queryset = queryset.filter(our_ref_no__icontains=our_ref_no)
        if status_param is not None:
            queryset = queryset.filter(status=status_param)
            
        return queryset

    @action(detail=False, methods=['post'], url_path='submit', serializer_class=CancellationCreateSerializer)
    def submit_cancellation(self, request):
        print("=" * 80)
        print("CANCELLATION SUBMIT - Received Data:", request.data)
        print("=" * 80)
        
        serializer = CancellationCreateSerializer(data=request.data)
        
        if not serializer.is_valid():
            print("❌ Serializer validation FAILED:")
            print("Errors:", serializer.errors)
            return Response({'error': 'Validation failed', 'details': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
        
        print("✅ Serializer validation PASSED")
        
        ref_no = serializer.validated_data['reference_no']
        permit_numbers = serializer.validated_data['permit_numbers']
        
        print(f"Reference No: {ref_no}")
        print(f"Permit Numbers: {permit_numbers}")
        
        # Never trust client-provided licensee_id for authenticated licensee users.
        if hasattr(request.user, 'supply_chain_profile'):
            licensee_id = request.user.supply_chain_profile.licensee_id
            print(f"Using licensee_id from profile: {licensee_id}")
        else:
            licensee_id = serializer.validated_data.get('licensee_id')
            if not licensee_id:
                return Response(
                    {'error': 'licensee_id is required when no supply-chain profile is active'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            print(f"Using licensee_id from request: {licensee_id}")

        try:
            # Fetch Requisition Data
            from models.transactional.supply_chain.ena_requisition_details.models import EnaRequisitionDetail
            req = EnaRequisitionDetail.objects.filter(our_ref_no=ref_no).first()

            if not req:
                print(f"❌ Requisition not found for ref_no: {ref_no}")
                return Response({'error': 'Requisition not found'}, status=status.HTTP_404_NOT_FOUND)
            
            print(f"✅ Found requisition: {req.id}")

            # Fixed fee per cancellation submission (aligned with revalidation style)
            total_amount = self.CANCELLATION_FEE_AMOUNT
            print(f"Total amount: {total_amount}")
            license_id = str(getattr(req, 'licensee_id', '') or '').strip()
            if not license_id:
                license_id = str(licensee_id or '').strip()

            # Fetch Workflow/Stage for Cancellation (CN_00)
            from auth.workflow.models import Workflow, WorkflowStage
            
            status_name = 'ForwardedCancellationToCommissioner' # Default Initial Status
            wf_obj = None
            current_stage = None
            
            try:
                 workflow = Workflow.objects.get(id=WORKFLOW_IDS['ENA_CANCELLATION'])
                 stage = WorkflowStage.objects.get(workflow=workflow, name=status_name)
                 
                 current_stage = stage
                 wf_obj = workflow
                 print(f"✅ Workflow setup successful: {workflow.name}, Stage: {stage.name}")
            except Exception as e:
                 print(f"⚠️ Workflow setup warning: {e}")
                 # Fallback to defaults already set

            # Generate cancellation reference
            cancel_ref = self._generate_cancellation_ref()
            print(f"Generated cancellation ref: {cancel_ref}")

            with transaction.atomic():
                # Prepare Cancellation Data
                cancellation = EnaCancellationDetail(
                    our_ref_no=cancel_ref,
                    requisition_date=req.requisition_date,
                    grain_ena_number=req.grain_ena_number,
                    bulk_spirit_type=req.bulk_spirit_type,
                    strength=req.strength,
                    lifted_from=req.lifted_from,
                    via_route=req.via_route,
                    # Workflow fields
                    workflow=wf_obj,
                    current_stage=current_stage,
                    # Legacy fields
                    status=status_name,
                    status_code='CN_00',

                    total_bl=req.totalbl,
                    requisiton_number_of_permits=req.requisiton_number_of_permits,
                    details_permits_number=req.details_permits_number,  # Copy from requisition
                    # Fields potentially missing in Requisition Model:
                    branch_name=req.lifted_from_distillery_name,
                    branch_address="N/A",
                    branch_purpose=req.branch_purpose,
                    govt_officer="N/A",
                    state=req.state,
                    cancellation_date=timezone.now(),
                    cancellation_br_amount=Decimal('0.00'),
                    cancelled_permit_number=",".join(permit_numbers),
                    total_cancellation_amount=Decimal(str(total_amount)),
                    permit_nocount=str(len(permit_numbers)),
                    licensee_id=licensee_id,
                    license_id=license_id,
                    distillery_name=req.lifted_from_distillery_name
                )

                print(f"✅ Copied details_permits_number from requisition: {req.details_permits_number}")
                print("Attempting to save cancellation...")
                cancellation.save()
                wallet_result = self._debit_wallet_for_cancellation_submission(
                    cancellation=cancellation,
                    user=request.user,
                    amount=Decimal(str(total_amount))
                )
            print(f"✅ Cancellation saved successfully with ID: {cancellation.id}")
            print("=" * 80)
            
            response_payload = {
                'message': 'Cancellation request submitted successfully!',
                'id': cancellation.id,
                'wallet_deduction': wallet_result
            }
            return Response(response_payload, status=status.HTTP_201_CREATED)

        except Exception as e:
            import traceback
            print("❌ ERROR occurred:")
            print(traceback.format_exc())
            print("=" * 80)
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['get'], url_path='generate_final_letter')
    def generate_final_letter(self, request, pk=None):
        """
        Generate final cancellation letter with proper permit numbers and dates
        """
        try:
            cancellation = self.get_object()
            
            # Parse cancelled permit numbers
            cancelled_permits = []
            if cancellation.cancelled_permit_number:
                cancelled_permits = [p.strip() for p in cancellation.cancelled_permit_number.split(',') if p.strip()]
            
            # Generate letter data
            letter_data = {
                'letter_number': f"No.{cancellation.id}/Excise",
                'letter_date': cancellation.cancellation_date.strftime('%d/%m/%Y') if cancellation.cancellation_date else timezone.now().strftime('%d/%m/%Y'),
                'addressee': {
                    'title': 'The Excise Officer-in-Charge,',
                    'company_name': cancellation.distillery_name,
                    'address': cancellation.branch_address or 'Address not available'
                },
                'subject': {
                    'permit_numbers': cancelled_permits,
                    'permit_date': cancellation.requisition_date.strftime('%d.%m.%Y') if cancellation.requisition_date else 'Date not available'
                },
                'reference': {
                    'letter_date': cancellation.cancellation_each_permit_date.strftime('%d.%m.%Y') if cancellation.cancellation_each_permit_date else cancellation.requisition_date.strftime('%d.%m.%Y') if cancellation.requisition_date else 'Date not available'
                },
                'cancellation_details': {
                    'reference_no': cancellation.our_ref_no,
                    'original_permit_numbers': cancelled_permits,
                    'original_permit_date': cancellation.requisition_date.strftime('%d.%m.%Y') if cancellation.requisition_date else 'Date not available',
                    'cancellation_date': cancellation.cancellation_date.strftime('%d.%m.%Y') if cancellation.cancellation_date else timezone.now().strftime('%d.%m.%Y'),
                    'distillery_name': cancellation.distillery_name,
                    'quantity': float(cancellation.grain_ena_number) if cancellation.grain_ena_number else 0,
                    'bulk_spirit_type': cancellation.bulk_spirit_type or 'Not specified',
                    'strength': cancellation.strength or 'Not specified',
                    'lifted_from': cancellation.lifted_from or 'Not specified',
                    'via_route': cancellation.via_route or 'Not specified',
                    'purpose': cancellation.branch_purpose or 'Not specified',
                    'number_of_permits': cancellation.requisiton_number_of_permits or 1,
                    'cancellation_amount': float(cancellation.cancellation_br_amount) if cancellation.cancellation_br_amount else 0,
                    'total_cancellation_amount': float(cancellation.total_cancellation_amount) if cancellation.total_cancellation_amount else 0,
                    'refund_amount': float(cancellation.total_cancellation_amount) - float(cancellation.cancellation_br_amount) if cancellation.total_cancellation_amount and cancellation.cancellation_br_amount else 0,
                    'status': cancellation.status,
                    'reason_for_cancellation': 'Cancellation requested by licensee',
                    'requested_by': 'Licensee',
                    'authorized_by': 'Commissioner of Excise'
                }
            }
            
            return Response(letter_data, status=status.HTTP_200_OK)
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=['post'], url_path='perform_action')
    def perform_action(self, request, pk=None):
        try:
            cancellation = self.get_object()
            action_type = request.data.get('action')
            remarks = request.data.get('remarks', f"Action {action_type} performed")
            
            # Use authenticated user from request
            user = request.user
            
            if not action_type:
                return Response({'error': 'Action is required'}, status=status.HTTP_400_BAD_REQUEST)

            if not has_workflow_access(user, WORKFLOW_IDS['ENA_CANCELLATION']) and not hasattr(user, 'supply_chain_profile'):
                return Response({'error': 'Unauthorized role for this workflow'}, status=status.HTTP_403_FORBIDDEN)
            
            from auth.workflow.services import WorkflowService
            
            # Ensure workflow/stage is set
            if not cancellation.workflow or not cancellation.current_stage:
                 from auth.workflow.models import Workflow, WorkflowStage
                 try:
                     wf = Workflow.objects.get(id=WORKFLOW_IDS['ENA_CANCELLATION'])
                     stage = WorkflowStage.objects.get(workflow=wf, name=cancellation.status)
                     cancellation.workflow = wf
                     cancellation.current_stage = stage
                     cancellation.save()
                 except Exception as e:
                     return Response({'error': f'Workflow state error: {e}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            # Match Logic
            try:
                # Find Transition
                target_transition = None
                transitions = WorkflowService.get_next_stages(cancellation)
                
                for t in transitions:
                    if transition_matches(t, user, action_type):
                        target_transition = t
                        break
                
                if not target_transition:
                    return Response({
                        'error': f'Invalid action {action_type} at stage {cancellation.current_stage.name}'
                    }, status=status.HTTP_400_BAD_REQUEST)

                # Use values from the matching transition condition to ensure validation passes
                context_data = target_transition.condition.copy() if target_transition.condition else {}
                
                WorkflowService.advance_stage(
                    application=cancellation,
                    user=user,
                    target_stage=target_transition.to_stage,
                    context=context_data,
                    remarks=remarks
                )
                
                # Update status
                cancellation.status = target_transition.to_stage.name
                # cancellation.status_code = ... # Removed dependency
                cancellation.save()

                return Response({
                    'message': f'Action {action_type} performed successfully',
                    'new_status': cancellation.status,
                    'new_status_code': cancellation.status_code
                })

            except ValueError as e:
                return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
            except PermissionError as e:
                return Response({'error': str(e)}, status=status.HTTP_403_FORBIDDEN)

        except Exception as e:
            import traceback
            traceback.print_exc()
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
