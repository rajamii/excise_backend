from rest_framework import generics
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.exceptions import PermissionDenied
from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction, models
from django.utils import timezone
from decimal import Decimal
import re
from .models import EnaRequisitionDetail, RequisitionBulkLiterDetail
from .serializers import EnaRequisitionDetailSerializer, RequisitionBulkLiterDetailSerializer
from auth.workflow.constants import WORKFLOW_IDS
from models.transactional.supply_chain.access_control import (
    has_workflow_access,
    scope_by_profile_or_workflow,
    transition_matches,
)


class EnaRequisitionDetailListCreateAPIView(generics.ListCreateAPIView):
    queryset = EnaRequisitionDetail.objects.all()
    serializer_class = EnaRequisitionDetailSerializer

    def get_queryset(self):
        queryset = EnaRequisitionDetail.objects.all()
        queryset = scope_by_profile_or_workflow(
            self.request.user,
            queryset,
            WORKFLOW_IDS['ENA_REQUISITION'],
            licensee_field='licensee_id'
        )

        our_ref_no = self.request.query_params.get('our_ref_no', None)
        if our_ref_no is not None:
            queryset = queryset.filter(our_ref_no=our_ref_no)
        return queryset
    
    def get_serializer_context(self):
        """
        Ensure request is passed to serializer context
        """
        context = super().get_serializer_context()
        context['request'] = self.request
        return context


class EnaRequisitionDetailRetrieveUpdateDestroyAPIView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = EnaRequisitionDetailSerializer

    def get_queryset(self):
        queryset = EnaRequisitionDetail.objects.all()
        queryset = scope_by_profile_or_workflow(
            self.request.user,
            queryset,
            WORKFLOW_IDS['ENA_REQUISITION'],
            licensee_field='licensee_id'
        )
        return queryset
    
    def get_serializer_context(self):
        """
        Ensure request is passed to serializer context
        """
        context = super().get_serializer_context()
        context['request'] = self.request
        return context


class GetNextRefNumberAPIView(APIView):
    """
    API endpoint to generate the next unique reference number.
    Format: REQ/{number:02d}/EXCISE
    
    Logic:
    - Queries all existing our_ref_no values
    - Extracts numeric parts and finds the maximum
    - Returns next sequential number
    - If all records are deleted, restarts from 1
    """
    def get(self, request):
        try:
            # Get all existing reference numbers
            existing_refs = EnaRequisitionDetail.objects.values_list('our_ref_no', flat=True)
            
            # Extract numeric parts from reference numbers
            numbers = []
            patterns = [r'REQ/(\d+)/EXCISE', r'IBPS/(\d+)/EXCISE']
            
            for ref in existing_refs:
                ref_text = str(ref or '')
                for pattern in patterns:
                    match = re.match(pattern, ref_text)
                    if match:
                        numbers.append(int(match.group(1)))
                        break
            
            # Determine next number
            if numbers:
                next_number = max(numbers) + 1
            else:
                next_number = 1
            
            # Format the reference number
            ref_number = f"REQ/{next_number:02d}/EXCISE"
            
            return Response({
                'status': 'success',
                'ref_number': ref_number,
                'next_sequence': next_number
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            return Response({
                'status': 'error',
                'message': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class RequisitionArrivalBulkLiterDetailAPIView(APIView):
    def _get_scoped_requisition(self, request, pk):
        queryset = scope_by_profile_or_workflow(
            request.user,
            EnaRequisitionDetail.objects.all(),
            WORKFLOW_IDS['ENA_REQUISITION'],
            licensee_field='licensee_id'
        )
        return queryset.get(pk=pk)

    def get(self, request, pk):
        try:
            requisition = self._get_scoped_requisition(request, pk)
            detail = RequisitionBulkLiterDetail.objects.filter(requisition=requisition).first()

            if not detail:
                return Response({
                    'status': 'success',
                    'message': 'No arrival details found.',
                    'data': None
                }, status=status.HTTP_200_OK)

            serializer = RequisitionBulkLiterDetailSerializer(detail)
            return Response({
                'status': 'success',
                'data': serializer.data
            }, status=status.HTTP_200_OK)

        except EnaRequisitionDetail.DoesNotExist:
            return Response({
                'status': 'error',
                'message': 'Requisition not found'
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({
                'status': 'error',
                'message': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def post(self, request, pk):
        try:
            is_licensee_user = (
                hasattr(request.user, 'supply_chain_profile')
                or hasattr(request.user, 'manufacturing_units')
            )
            if not is_licensee_user:
                return Response({
                    'status': 'error',
                    'message': 'Only licensee users can update arrival details.'
                }, status=status.HTTP_403_FORBIDDEN)

            requisition = self._get_scoped_requisition(request, pk)

            payload = request.data.copy()
            payload['requisition'] = requisition.id
            payload['reference_no'] = requisition.our_ref_no
            payload['licensee_id'] = requisition.licensee_id

            existing = RequisitionBulkLiterDetail.objects.filter(requisition=requisition).first()
            serializer = RequisitionBulkLiterDetailSerializer(
                existing,
                data=payload,
                partial=bool(existing)
            )
            serializer.is_valid(raise_exception=True)
            record = serializer.save(
                reference_no=requisition.our_ref_no,
                licensee_id=requisition.licensee_id
            )

            return Response({
                'status': 'success',
                'message': 'Arrival details saved successfully.',
                'data': RequisitionBulkLiterDetailSerializer(record).data
            }, status=status.HTTP_200_OK if existing else status.HTTP_201_CREATED)

        except EnaRequisitionDetail.DoesNotExist:
            return Response({
                'status': 'error',
                'message': 'Requisition not found'
            }, status=status.HTTP_404_NOT_FOUND)
        except PermissionDenied as e:
            return Response({
                'status': 'error',
                'message': str(e)
            }, status=status.HTTP_403_FORBIDDEN)
        except Exception as e:
            return Response({
                'status': 'error',
                'message': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class RequisitionArrivalBulkLiterDetailsListAPIView(APIView):
    def _expand_license_aliases(self, value: str):
        token = str(value or '').strip()
        if not token:
            return []
        aliases = [token]
        if token.startswith('NLI/'):
            aliases.append(f"NA/{token[4:]}")
        elif token.startswith('NA/'):
            aliases.append(f"NLI/{token[3:]}")
        return aliases

    def get(self, request):
        try:
            requisitions = scope_by_profile_or_workflow(
                request.user,
                EnaRequisitionDetail.objects.all(),
                WORKFLOW_IDS['ENA_REQUISITION'],
                licensee_field='licensee_id'
            )
            requisition_ids = list(requisitions.values_list('id', flat=True))
            if not requisition_ids:
                return Response({
                    'status': 'success',
                    'data': []
                }, status=status.HTTP_200_OK)

            licensee_candidates = set()
            if hasattr(request.user, 'supply_chain_profile'):
                for alias in self._expand_license_aliases(getattr(request.user.supply_chain_profile, 'licensee_id', '')):
                    licensee_candidates.add(alias)
            if hasattr(request.user, 'manufacturing_units'):
                for raw_id in request.user.manufacturing_units.exclude(licensee_id__isnull=True).exclude(licensee_id='').values_list('licensee_id', flat=True):
                    for alias in self._expand_license_aliases(raw_id):
                        licensee_candidates.add(alias)

            rows_qs = RequisitionBulkLiterDetail.objects.select_related('requisition').filter(
                requisition_id__in=requisition_ids
            ).order_by('-updated_at')
            if licensee_candidates:
                license_q = models.Q()
                for cid in licensee_candidates:
                    token = str(cid or '').strip()
                    if token:
                        license_q |= models.Q(licensee_id__iexact=token)
                if license_q:
                    rows_qs = rows_qs.filter(license_q)
                if not rows_qs.exists():
                    ref_nos = list(
                        requisitions.exclude(our_ref_no__isnull=True).exclude(our_ref_no='').values_list('our_ref_no', flat=True)
                    )
                    if ref_nos:
                        rows_qs = RequisitionBulkLiterDetail.objects.filter(
                            requisition_id__in=requisition_ids,
                            reference_no__in=ref_nos
                        ).select_related('requisition').order_by('-updated_at')
            rows = rows_qs

            data = []
            for row in rows:
                req = getattr(row, 'requisition', None)
                data.append({
                    'id': row.id,
                    'requisition_id': req.id if req else None,
                    'reference_no': row.reference_no,
                    'licensee_id': row.licensee_id,
                    'tanker_count': row.tanker_count,
                    'tanker_details': row.tanker_details or [],
                    'total_bulk_liter': str(row.total_bulk_liter or 0),
                    'arrival_date': row.updated_at.date().isoformat() if row.updated_at else '',
                    'requisition_total_quantity': str(getattr(req, 'totalbl', 0) or 0) if req else '0',
                    'distillery_name': (getattr(req, 'lifted_from_distillery_name', '') or '') if req else '',
                    'approval_date': getattr(req, 'approval_date', None) if req else None,
                })

            return Response({
                'status': 'success',
                'data': data
            }, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({
                'status': 'error',
                'message': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class PerformRequisitionActionAPIView(APIView):
    """
    API endpoint to perform an action (APPROVE/REJECT) on a requisition.
    Dynamically determines the next status based on the current status and the action
    by querying the WorkflowRule table.
    """

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

    def _resolve_wallet_license_candidates(self, requisition, user):
        candidates = []

        req_license = str(getattr(requisition, 'licensee_id', '') or '').strip()
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

    def _is_forwarded_payslip_stage(self, stage_name: str) -> bool:
        token = ''.join(ch for ch in str(stage_name or '').lower() if ch.isalnum())
        return (
            token == 'forwardedpaysliptopermitsection'
            or ('forwarded' in token and 'payslip' in token and 'permitsection' in token)
        )

    def _resolve_requisition_payment_amount(self, requisition) -> Decimal:
        """
        Resolve payable amount for requisition debit using:
        selected bulk spirit price_bl * totalbl.
        """
        total_bl_raw = getattr(requisition, 'totalbl', None)
        try:
            total_bl = Decimal(str(total_bl_raw))
        except Exception:
            total_bl = Decimal('0')
        if total_bl <= 0:
            return Decimal('0')

        spirit_kind = str(getattr(requisition, 'bulk_spirit_type', '') or '').strip()
        strength = str(getattr(requisition, 'strength', '') or '').strip()
        if not spirit_kind:
            return Decimal('0')

        try:
            from models.masters.supply_chain.bulk_spirit.models import BulkSpiritType
            qs = BulkSpiritType.objects.filter(
                bulk_spirit_kind_type__iexact=spirit_kind
            )
            if strength:
                qs = qs.filter(strength__iexact=strength)
            row = qs.order_by('sprit_id').first()
            if row and row.price_bl is not None:
                return Decimal(str(row.price_bl)) * total_bl
        except Exception:
            pass

        return Decimal('0')

    def _debit_wallet_for_requisition_payment(self, requisition, user, target_stage_name: str):
        from models.transactional.payment.models import WalletBalance, WalletTransaction

        amount = self._resolve_requisition_payment_amount(requisition)
        if amount <= 0:
            return {'debited': False, 'reason': 'zero_amount'}

        reference_no = str(getattr(requisition, 'our_ref_no', '') or f"REQ-{requisition.pk}")
        transaction_id = f"REQ-{requisition.pk}-PAYMENT"

        already_debited = WalletTransaction.objects.filter(
            transaction_id=transaction_id,
            source_module='ena_requisition',
            entry_type='DR'
        ).exists()
        if already_debited:
            return {'debited': False, 'reason': 'already_debited'}

        candidates = self._resolve_wallet_license_candidates(requisition, user)
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
            source_module='ena_requisition',
            payment_status='success',
            remarks=f"Requisition payment debit on stage {target_stage_name}",
            created_at=now_ts,
        )

        return {
            'debited': True,
            'licensee_id': resolved_licensee_id,
            'wallet_type': wallet.wallet_type,
            'amount': str(amount)
        }

    def post(self, request, pk):
        try:
             # from models.masters.supply_chain.status_master.models import StatusMaster, WorkflowRule # Removed
            
            action = request.data.get('action')
            if not action or action not in ['APPROVE', 'REJECT']:
                return Response({
                    'status': 'error',
                    'message': 'Valid action (APPROVE or REJECT) is required'
                }, status=status.HTTP_400_BAD_REQUEST)

            # Get the requisition
            requisition = EnaRequisitionDetail.objects.get(pk=pk)

            # Licensee users can only act on their own requisitions.
            if hasattr(request.user, 'supply_chain_profile'):
                user_licensee_id = request.user.supply_chain_profile.licensee_id
                if str(requisition.licensee_id) != str(user_licensee_id):
                    raise PermissionDenied("You are not allowed to modify this requisition.")
            if not has_workflow_access(request.user, WORKFLOW_IDS['ENA_REQUISITION']) and not hasattr(request.user, 'supply_chain_profile'):
                return Response({
                    'status': 'error',
                    'message': 'Unauthorized role for this workflow'
                }, status=status.HTTP_403_FORBIDDEN)

            # --- Use WorkflowService to advance stage ---
            from auth.workflow.services import WorkflowService
            from auth.workflow.models import WorkflowStage
            
            # Ensure current_stage is set (if missing for some reason)
            if not requisition.current_stage:
                 try:
                     if requisition.workflow_id:
                         current_stage = WorkflowStage.objects.get(workflow_id=requisition.workflow_id, name=requisition.status)
                     else:
                         current_stage = WorkflowStage.objects.get(
                             workflow_id=WORKFLOW_IDS['ENA_REQUISITION'],
                             name=requisition.status
                         )
                     requisition.current_stage = current_stage
                     requisition.save()
                 except WorkflowStage.DoesNotExist:
                     return Response({'status': 'error', 'message': f'Current stage undefined and could not be inferred from status {requisition.status}'}, status=400)
            
            # Context for validation (if rules use condition)
            context = {
                "action": action
            }

            # WorkflowService.advance_stage expects:
            # - application
            # - user
            # - target_stage (We need to find this first via validate_transition logic or just find it ourselves)
            
            # Actually, WorkflowService.advance_stage takes `target_stage`. We need to determine which stage is next.
            # WorkflowService.get_next_stages(application) returns generic transitions.
            # We filter for the one matching our role/action.
            
            transitions = WorkflowService.get_next_stages(requisition)
            target_transition = None
            
            for t in transitions:
                if transition_matches(t, request.user, action):
                    target_transition = t
                    break
            
            if not target_transition:
                return Response({
                    'status': 'error',
                    'message': f'No valid transition for Action: {action} on Stage: {requisition.current_stage.name}'
                }, status=status.HTTP_400_BAD_REQUEST)
                
            try:
                with transaction.atomic():
                    WorkflowService.advance_stage(
                        application=requisition,
                        user=request.user,
                        target_stage=target_transition.to_stage,
                        context=context, # Context might be used for extra validation in service
                        remarks=f"Action: {action}"
                    )

                    # Sync back to status/status_code for legacy
                    # from models.masters.supply_chain.status_master.models import StatusMaster # Removed
                    new_stage_name = target_transition.to_stage.name
                    requisition.status = new_stage_name

                    # status_obj = StatusMaster.objects.filter(status_name=new_stage_name).first() # Removed
                    # if status_obj:
                    #     requisition.status_code = status_obj.status_code

                    requisition.save() # status update

                    wallet_result = None
                    if action == 'APPROVE' and self._is_forwarded_payslip_stage(new_stage_name):
                        wallet_result = self._debit_wallet_for_requisition_payment(
                            requisition=requisition,
                            user=request.user,
                            target_stage_name=new_stage_name
                        )

                # Return updated requisition
                serializer = EnaRequisitionDetailSerializer(requisition)
                response_payload = {
                    'status': 'success',
                    'message': f'Requisition status updated to {new_stage_name}',
                    'data': serializer.data
                }
                if wallet_result is not None:
                    response_payload['wallet_deduction'] = wallet_result
                return Response(response_payload, status=status.HTTP_200_OK)

            except (PermissionDenied, DjangoPermissionDenied) as e:
                return Response({
                    'status': 'error',
                    'message': str(e)
                }, status=status.HTTP_403_FORBIDDEN)
            except DjangoValidationError as e:
                return Response({
                    'status': 'error',
                    'message': str(e)
                }, status=status.HTTP_400_BAD_REQUEST)
            except Exception as e:
                 return Response({
                    'status': 'error',
                    'message': str(e)
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        except EnaRequisitionDetail.DoesNotExist:
            return Response({
                'status': 'error',
                'message': 'Requisition not found'
            }, status=status.HTTP_404_NOT_FOUND)
        except (PermissionDenied, DjangoPermissionDenied) as e:
            return Response({
                'status': 'error',
                'message': str(e)
            }, status=status.HTTP_403_FORBIDDEN)
        except DjangoValidationError as e:
            return Response({
                'status': 'error',
                'message': str(e)
            }, status=status.HTTP_400_BAD_REQUEST)
            
        except Exception as e:
            return Response({
                'status': 'error',
                'message': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)



