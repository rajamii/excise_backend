from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.utils import timezone
from django.db import transaction, models
from decimal import Decimal
import logging
import re
from .models import EnaCancellationDetail
from .serializers import EnaCancellationDetailSerializer, CancellationCreateSerializer
from auth.workflow.constants import WORKFLOW_IDS
from models.transactional.supply_chain.access_control import (
    has_workflow_access,
    scope_by_profile_or_workflow,
    transition_matches,
)

logger = logging.getLogger(__name__)

class EnaCancellationDetailViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows ENA cancellation details to be viewed or edited.
    """
    queryset = EnaCancellationDetail.objects.all().order_by('-created_at')
    serializer_class = EnaCancellationDetailSerializer
    permission_classes = [permissions.IsAuthenticated]
    CANCELLATION_FEE_AMOUNT = Decimal('1000.00')

    def _resolve_cancellation_amount(self, cancellation) -> Decimal:
        # cancellation_br_amount stores the fee debit; total_cancellation_amount stores the refund credit.
        amount = Decimal(str(getattr(cancellation, 'cancellation_br_amount', 0) or 0))
        if amount <= 0:
            amount = Decimal(str(getattr(cancellation, 'total_cancellation_amount', 0) or 0))

        if amount > 0:
            return amount

        permit_numbers_raw = (
            getattr(cancellation, 'cancelled_permit_numbers', None)
            or getattr(cancellation, 'cancelled_permit_number', None)
            or ''
        )
        permit_count = len([num.strip() for num in str(permit_numbers_raw).split(',') if num.strip()])

        if permit_count <= 0:
            try:
                permit_count = int(str(getattr(cancellation, 'permit_nocount', '') or '0'))
            except Exception:
                permit_count = 0

        if permit_count > 0:
            return self.CANCELLATION_FEE_AMOUNT * Decimal(permit_count)

        return Decimal('0')

    def _resolve_requisition_total_payment_amount(self, requisition) -> Decimal:
        try:
            total_bl = Decimal(str(getattr(requisition, 'totalbl', '0') or '0'))
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
                amount = Decimal(str(row.price_bl or 0)) * total_bl
                return amount.quantize(Decimal('0.01'))
        except Exception:
            pass

        return Decimal('0')

    def _try_auto_sync_wallet_debit(self, cancellation, user):
        try:
            if self._is_rejected_cancellation(cancellation):
                return

            fee_amount = self._resolve_cancellation_amount(cancellation)
            refund_amount = self._resolve_permit_refund_amount(cancellation)
            if fee_amount <= 0 and refund_amount <= 0:
                return

            with transaction.atomic():
                self._apply_wallet_refund_and_fee_for_cancellation_submission(
                    cancellation=cancellation,
                    user=user,
                    refund_amount=refund_amount,
                    fee_amount=fee_amount,
                )
        except Exception:
            logger.exception(
                "Auto wallet debit sync failed for cancellation_id=%s ref=%s user=%s",
                getattr(cancellation, "id", None),
                getattr(cancellation, "our_ref_no", None),
                getattr(user, "username", None),
            )

    def _normalize_stage_text(self, value: str) -> str:
        return re.sub(r'[^a-z0-9]+', '', str(value or '').lower())

    def _resolve_stage_for_workflow(self, workflow, status_hint: str = ''):
        from auth.workflow.models import WorkflowStage

        stages = list(WorkflowStage.objects.filter(workflow=workflow))
        if not stages:
            return None

        hint = self._normalize_stage_text(status_hint)
        if hint:
            for stage in stages:
                if self._normalize_stage_text(stage.name) == hint:
                    return stage

            keywords = [
                key for key in ['forward', 'approve', 'reject', 'payslip', 'payment', 'commissioner']
                if key in hint
            ]
            if keywords:
                scored = []
                for stage in stages:
                    stage_text = self._normalize_stage_text(stage.name)
                    score = sum(1 for key in keywords if key in stage_text)
                    scored.append((score, stage))
                best_score, best_stage = max(scored, key=lambda item: item[0])
                if best_score > 0:
                    return best_stage

        initial_stage = next((stage for stage in stages if stage.is_initial), None)
        return initial_stage or stages[0]

    def _is_rejected_cancellation(self, cancellation) -> bool:
        current_stage_name = getattr(getattr(cancellation, 'current_stage', None), 'name', '')
        merged = f"{getattr(cancellation, 'status', '')} {current_stage_name}".lower()
        return 'reject' in merged

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

        profile_license = ''
        if hasattr(user, 'supply_chain_profile'):
            profile_license = str(getattr(user.supply_chain_profile, 'licensee_id', '') or '').strip()
        candidates.extend(self._expand_license_aliases(profile_license))

        cancellation_license_id = str(getattr(cancellation, 'license_id', '') or '').strip()
        candidates.extend(self._expand_license_aliases(cancellation_license_id))

        req_licensee = str(getattr(cancellation, 'licensee_id', '') or '').strip()
        candidates.extend(self._expand_license_aliases(req_licensee))

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
        # Backward-compatible wrapper retained for older callers.
        # New logic uses _apply_wallet_refund_and_fee_for_cancellation_submission.
        from models.transactional.payment.models import WalletBalance, WalletTransaction

        amount_decimal = Decimal(str(amount or 0))
        if amount_decimal <= 0:
            return {'debited': False, 'reason': 'zero_amount'}

        reference_no = str(getattr(cancellation, 'our_ref_no', '') or f"CAN-{cancellation.pk}")
        transaction_id = f"CAN-{cancellation.pk}-PAYMENT"

        already_debited = WalletTransaction.objects.filter(
            transaction_id=transaction_id,
            entry_type='DR',
            source_module='ena_cancellation',
            reference_no=reference_no,
        ).exists()
        if already_debited:
            existing = (
                WalletTransaction.objects.filter(
                    transaction_id=transaction_id,
                    entry_type='DR',
                    source_module='ena_cancellation',
                    reference_no=reference_no,
                )
                .order_by('-created_at', '-wallet_transaction_id')
                .first()
            )
            return {
                'debited': False,
                'reason': 'already_debited',
                'transaction_id': transaction_id,
                'reference_no': reference_no,
                'licensee_id': str(getattr(existing, 'licensee_id', '') or ''),
                'wallet_type': str(getattr(existing, 'wallet_type', '') or ''),
                'amount': str(getattr(existing, 'amount', '') or ''),
                'balance_before': str(getattr(existing, 'balance_before', '') or ''),
                'balance_after': str(getattr(existing, 'balance_after', '') or ''),
            }

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
            'licensee_id': resolved_license_id,
            'wallet_type': wallet.wallet_type,
            'amount': str(amount_decimal),
            'balance_before': str(current_balance),
            'balance_after': str(after),
            'transaction_id': transaction_id,
            'reference_no': reference_no,
        }

    def _resolve_permit_refund_amount(self, cancellation) -> Decimal:
        """
        Amount to be refunded back to wallet when cancellation is requested.
        Stored on the cancellation row as the total refund across selected permits.
        """
        amount = Decimal(str(getattr(cancellation, 'total_cancellation_amount', 0) or 0))
        if amount > 0:
            return amount.quantize(Decimal('0.01'))
        return Decimal('0')

    def _apply_wallet_refund_and_fee_for_cancellation_submission(
        self,
        cancellation,
        user,
        refund_amount: Decimal,
        fee_amount: Decimal,
    ):
        """
        Apply both wallet operations atomically (idempotent):
        - Refund (credit) selected permit amount back to wallet
        - Deduct (debit) cancellation fee
        """
        from models.transactional.payment.models import WalletBalance, WalletTransaction

        refund_amount = Decimal(str(refund_amount or 0)).quantize(Decimal('0.01'))
        fee_amount = Decimal(str(fee_amount or 0)).quantize(Decimal('0.01'))

        reference_no = str(getattr(cancellation, 'our_ref_no', '') or f"CAN-{cancellation.pk}")
        refund_txn_id = f"CAN-{cancellation.pk}-REFUND"
        fee_txn_id = f"CAN-{cancellation.pk}-FEE"
        legacy_fee_txn_id = f"CAN-{cancellation.pk}-PAYMENT"

        candidates = self._resolve_wallet_license_candidates(cancellation, user)
        if not candidates:
            raise ValueError("Unable to resolve license id for wallet operation.")

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

        existing_refund = (
            WalletTransaction.objects.filter(
                transaction_id=refund_txn_id,
                entry_type='CR',
                source_module='ena_cancellation',
                reference_no=reference_no,
            )
            .order_by('-created_at', '-wallet_transaction_id')
            .first()
        )

        existing_fee = (
            WalletTransaction.objects.filter(
                entry_type='DR',
                source_module='ena_cancellation',
                reference_no=reference_no,
                transaction_id__in=[fee_txn_id, legacy_fee_txn_id],
            )
            .order_by('-created_at', '-wallet_transaction_id')
            .first()
        )

        now_ts = timezone.now()
        starting_balance = Decimal(str(wallet.current_balance or 0)).quantize(Decimal('0.01'))
        current_balance = starting_balance
        total_credit = Decimal(str(wallet.total_credit or 0)).quantize(Decimal('0.01'))
        total_debit = Decimal(str(wallet.total_debit or 0)).quantize(Decimal('0.01'))

        refund_result = None
        fee_result = None

        if existing_refund:
            refund_result = {
                'credited': False,
                'reason': 'already_credited',
                'transaction_id': str(existing_refund.transaction_id or refund_txn_id),
                'reference_no': reference_no,
                'licensee_id': str(getattr(existing_refund, 'licensee_id', '') or ''),
                'wallet_type': str(getattr(existing_refund, 'wallet_type', '') or ''),
                'amount': str(getattr(existing_refund, 'amount', '') or ''),
                'balance_before': str(getattr(existing_refund, 'balance_before', '') or ''),
                'balance_after': str(getattr(existing_refund, 'balance_after', '') or ''),
            }
        elif refund_amount > 0:
            after = (current_balance + refund_amount).quantize(Decimal('0.01'))
            WalletTransaction.objects.create(
                wallet_balance=wallet,
                transaction_id=refund_txn_id,
                licensee_id=resolved_license_id,
                licensee_name=wallet.licensee_name,
                user_id=str(getattr(user, 'username', '') or wallet.user_id or ''),
                module_type=wallet.module_type,
                wallet_type=wallet.wallet_type,
                head_of_account=wallet.head_of_account,
                entry_type='CR',
                transaction_type='refund',
                amount=refund_amount,
                balance_before=current_balance,
                balance_after=after,
                reference_no=reference_no,
                source_module='ena_cancellation',
                payment_status='refunded',
                remarks='Permit amount refund on cancellation submission',
                created_at=now_ts,
            )
            total_credit = (total_credit + refund_amount).quantize(Decimal('0.01'))
            current_balance = after
            refund_result = {
                'credited': True,
                'licensee_id': resolved_license_id,
                'wallet_type': wallet.wallet_type,
                'amount': str(refund_amount),
                'balance_before': str((after - refund_amount).quantize(Decimal('0.01'))),
                'balance_after': str(after),
                'transaction_id': refund_txn_id,
                'reference_no': reference_no,
            }
        else:
            refund_result = {'credited': False, 'reason': 'zero_amount'}

        if existing_fee:
            fee_result = {
                'debited': False,
                'reason': 'already_debited',
                'transaction_id': str(existing_fee.transaction_id or fee_txn_id),
                'reference_no': reference_no,
                'licensee_id': str(getattr(existing_fee, 'licensee_id', '') or ''),
                'wallet_type': str(getattr(existing_fee, 'wallet_type', '') or ''),
                'amount': str(getattr(existing_fee, 'amount', '') or ''),
                'balance_before': str(getattr(existing_fee, 'balance_before', '') or ''),
                'balance_after': str(getattr(existing_fee, 'balance_after', '') or ''),
            }
        elif fee_amount > 0:
            if current_balance < fee_amount:
                raise ValueError(
                    f"Insufficient wallet balance. Available: {current_balance}, Required: {fee_amount}"
                )
            after = (current_balance - fee_amount).quantize(Decimal('0.01'))
            WalletTransaction.objects.create(
                wallet_balance=wallet,
                transaction_id=fee_txn_id,
                licensee_id=resolved_license_id,
                licensee_name=wallet.licensee_name,
                user_id=str(getattr(user, 'username', '') or wallet.user_id or ''),
                module_type=wallet.module_type,
                wallet_type=wallet.wallet_type,
                head_of_account=wallet.head_of_account,
                entry_type='DR',
                transaction_type='debit',
                amount=fee_amount,
                balance_before=current_balance,
                balance_after=after,
                reference_no=reference_no,
                source_module='ena_cancellation',
                payment_status='success',
                remarks='Cancellation fee debit',
                created_at=now_ts,
            )
            total_debit = (total_debit + fee_amount).quantize(Decimal('0.01'))
            current_balance = after
            fee_result = {
                'debited': True,
                'licensee_id': resolved_license_id,
                'wallet_type': wallet.wallet_type,
                'amount': str(fee_amount),
                'balance_before': str((after + fee_amount).quantize(Decimal('0.01'))),
                'balance_after': str(after),
                'transaction_id': fee_txn_id,
                'reference_no': reference_no,
            }
        else:
            fee_result = {'debited': False, 'reason': 'zero_amount'}

        wallet.current_balance = current_balance
        wallet.total_credit = total_credit
        wallet.total_debit = total_debit
        wallet.last_updated_at = now_ts
        wallet.save(update_fields=['current_balance', 'total_credit', 'total_debit', 'last_updated_at'])

        return {
            'licensee_id': resolved_license_id,
            'wallet_type': wallet.wallet_type,
            'reference_no': reference_no,
            'balance_before': str(starting_balance),
            'balance_after': str(current_balance),
            'refund': refund_result,
            'fee': fee_result,
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
        requisition_ref_no = self.request.query_params.get('requisition_ref_no', None)
        status_param = self.request.query_params.get('status', None)
        
        if our_ref_no is not None:
            queryset = queryset.filter(our_ref_no__icontains=our_ref_no)
        if requisition_ref_no is not None:
            queryset = queryset.filter(requisition_ref_no__icontains=requisition_ref_no)
        if status_param is not None:
            queryset = queryset.filter(status=status_param)
            
        return queryset

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())

        # Server-side self-heal for licensee view:
        # when a cancellation exists but wallet debit row is missing, create it idempotently.
        if hasattr(request.user, 'supply_chain_profile'):
            for cancellation in queryset:
                self._try_auto_sync_wallet_debit(cancellation, request.user)

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['post'], url_path='submit', serializer_class=CancellationCreateSerializer)
    def submit_cancellation(self, request):
        logger.debug("ENA cancellation submit request received")
        
        serializer = CancellationCreateSerializer(data=request.data)
        
        if not serializer.is_valid():
            logger.debug("ENA cancellation submit validation failed: %s", serializer.errors)
            return Response({'error': 'Validation failed', 'details': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
        logger.debug("ENA cancellation submit validation passed")
        
        ref_no = serializer.validated_data['reference_no']
        permit_numbers = serializer.validated_data['permit_numbers']
        normalized_permit_numbers = [str(num).strip() for num in permit_numbers if str(num).strip()]
        logger.debug("ENA cancellation submit: ref_no=%s permit_count=%s", ref_no, len(normalized_permit_numbers))

        if not normalized_permit_numbers:
            return Response(
                {'error': 'At least one permit number must be selected for cancellation.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Never trust client-provided licensee_id for authenticated licensee users.
        if hasattr(request.user, 'supply_chain_profile'):
            licensee_id = request.user.supply_chain_profile.licensee_id
        else:
            licensee_id = serializer.validated_data.get('licensee_id')
            if not licensee_id:
                return Response(
                    {'error': 'licensee_id is required when no supply-chain profile is active'},
                    status=status.HTTP_400_BAD_REQUEST
                )

        try:
            # Fetch Requisition Data
            from models.transactional.supply_chain.ena_requisition_details.models import EnaRequisitionDetail
            req = EnaRequisitionDetail.objects.filter(our_ref_no=ref_no).first()

            if not req:
                logger.info("ENA cancellation submit: requisition not found for ref_no=%s", ref_no)
                return Response({'error': 'Requisition not found'}, status=status.HTTP_404_NOT_FOUND)
            
            logger.debug("ENA cancellation submit: requisition found id=%s", req.id)

            existing_cancellations = EnaCancellationDetail.objects.filter(requisition_ref_no=ref_no)
            blocked_permits = set()
            for existing in existing_cancellations:
                if self._is_rejected_cancellation(existing):
                    continue

                existing_numbers_raw = (
                    existing.cancelled_permit_numbers
                    or existing.cancelled_permit_number
                    or ''
                )
                existing_numbers = [
                    num.strip() for num in str(existing_numbers_raw).split(',') if num.strip()
                ]
                blocked_permits.update(existing_numbers)

            duplicate_permits = sorted(
                set(normalized_permit_numbers) & blocked_permits,
                key=lambda value: int(value) if value.isdigit() else value
            )
            if duplicate_permits:
                return Response({
                    'error': 'Some selected permits are already submitted for cancellation.',
                    'duplicate_permits': duplicate_permits
                }, status=status.HTTP_400_BAD_REQUEST)

            # Cancellation fee is fixed per permit, while refund comes from the requisition's
            # actual payment amount split evenly across its permits.
            permit_count = Decimal(len(normalized_permit_numbers))
            cancellation_fee_amount = (self.CANCELLATION_FEE_AMOUNT * permit_count).quantize(Decimal('0.01'))
            total_requisition_payment_amount = self._resolve_requisition_total_payment_amount(req)
            requisition_permit_count = Decimal(str(getattr(req, 'requisiton_number_of_permits', 0) or 0))
            if requisition_permit_count <= 0:
                requisition_permit_count = permit_count

            per_permit_refund_amount = Decimal('0.00')
            if total_requisition_payment_amount > 0 and requisition_permit_count > 0:
                per_permit_refund_amount = (
                    total_requisition_payment_amount / requisition_permit_count
                ).quantize(Decimal('0.01'))

            permit_refund_amount = (per_permit_refund_amount * permit_count).quantize(Decimal('0.01'))
            logger.debug(
                "ENA cancellation submit: fee=%s refund=%s per_permit_refund=%s permits=%s",
                cancellation_fee_amount,
                permit_refund_amount,
                per_permit_refund_amount,
                len(normalized_permit_numbers),
            )
            license_id = str(licensee_id or '').strip()
            if not license_id:
                license_id = str(getattr(req, 'licensee_id', '') or '').strip()

            # Fetch workflow/stage dynamically (works even after stage label renames).
            from auth.workflow.models import Workflow

            status_name = 'CancellationPending'
            wf_obj = None
            current_stage = None
            
            try:
                 workflow = Workflow.objects.get(id=WORKFLOW_IDS['ENA_CANCELLATION'])
                 stage = self._resolve_stage_for_workflow(workflow=workflow)
                 if stage:
                     current_stage = stage
                     status_name = stage.name
                 wf_obj = workflow
                 logger.debug(
                     "ENA cancellation submit: workflow setup ok workflow=%s stage=%s",
                     getattr(workflow, "name", None),
                     getattr(stage, "name", "N/A"),
                 )
            except Exception as e:
                 logger.warning("ENA cancellation submit: workflow setup warning", exc_info=True)
                 # Fallback to defaults already set

            # Generate cancellation reference
            cancel_ref = self._generate_cancellation_ref()
            logger.debug("ENA cancellation submit: generated cancellation ref=%s", cancel_ref)

            with transaction.atomic():
                # Prepare Cancellation Data
                cancellation = EnaCancellationDetail(
                    our_ref_no=cancel_ref,
                    requisition_ref_no=ref_no,
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
                    # cancellation_br_amount = cancellation fee debit
                    cancellation_br_amount=Decimal(str(cancellation_fee_amount)),
                    cancelled_permit_number=",".join(normalized_permit_numbers),
                    cancelled_permit_numbers=",".join(normalized_permit_numbers),
                    # total_cancellation_amount = total permit amount refunded
                    total_cancellation_amount=Decimal(str(permit_refund_amount)),
                    permit_nocount=str(len(normalized_permit_numbers)),
                    licensee_id=licensee_id,
                    license_id=license_id,
                    distillery_name=req.lifted_from_distillery_name
                )

                logger.debug(
                    "ENA cancellation submit: copying details_permits_number=%s",
                    getattr(req, "details_permits_number", None),
                )
                cancellation.save()
                wallet_effects = self._apply_wallet_refund_and_fee_for_cancellation_submission(
                    cancellation=cancellation,
                    user=request.user,
                    refund_amount=permit_refund_amount,
                    fee_amount=cancellation_fee_amount,
                )
            logger.info("ENA cancellation submitted successfully (id=%s)", cancellation.id)
            
            response_payload = {
                'message': 'Cancellation request submitted successfully!',
                'id': cancellation.id,
                # Backward-compatible keys
                'wallet_deduction': wallet_effects.get('fee'),
                'wallet_refund': wallet_effects.get('refund'),
                # New structured payload
                'wallet_effects': wallet_effects,
            }
            return Response(response_payload, status=status.HTTP_201_CREATED)

        except Exception as e:
            logger.exception("Unhandled error during ENA cancellation submit")
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
            cancelled_permits_raw = (
                cancellation.cancelled_permit_numbers
                or cancellation.cancelled_permit_number
                or ''
            )
            if cancelled_permits_raw:
                cancelled_permits = [p.strip() for p in cancelled_permits_raw.split(',') if p.strip()]
            
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
            logger.exception("Unhandled error while generating cancellation letter")
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
            normalized_action = self._normalize_stage_text(action_type)
            wallet_result = None
            
            # Ensure workflow/stage is set (with compatibility for renamed stage labels).
            if not cancellation.workflow:
                 from auth.workflow.models import Workflow
                 try:
                     cancellation.workflow = Workflow.objects.get(id=WORKFLOW_IDS['ENA_CANCELLATION'])
                 except Exception as e:
                     return Response({'error': f'Workflow state error: {e}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            if not cancellation.current_stage:
                 try:
                     stage = self._resolve_stage_for_workflow(
                         workflow=cancellation.workflow,
                         status_hint=cancellation.status
                     )
                     if not stage:
                         return Response({'error': 'Workflow stage resolution failed'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

                     cancellation.current_stage = stage
                     cancellation.status = stage.name
                     cancellation.save(update_fields=['workflow', 'current_stage', 'status', 'updated_at'])
                 except Exception as e:
                     return Response({'error': f'Workflow state error: {e}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            # Match Logic
            try:
                with transaction.atomic():
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

                    # Apply wallet effects on licensee pay action (SubmitPayslip) if not already applied.
                    if normalized_action in ['submitpayslip', 'payslip', 'pay', 'payment']:
                        fee_amount = self._resolve_cancellation_amount(cancellation)
                        refund_amount = self._resolve_permit_refund_amount(cancellation)
                        wallet_effects = self._apply_wallet_refund_and_fee_for_cancellation_submission(
                            cancellation=cancellation,
                            user=user,
                            refund_amount=refund_amount,
                            fee_amount=fee_amount,
                        )

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

                response = {
                    'message': f'Action {action_type} performed successfully',
                    'new_status': cancellation.status,
                    'new_status_code': cancellation.status_code
                }
                if 'wallet_effects' in locals() and wallet_effects is not None:
                    response['wallet_deduction'] = wallet_effects.get('fee')
                    response['wallet_refund'] = wallet_effects.get('refund')
                    response['wallet_effects'] = wallet_effects
                return Response(response)

            except ValueError as e:
                return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
            except PermissionError as e:
                return Response({'error': str(e)}, status=status.HTTP_403_FORBIDDEN)

        except Exception as e:
            logger.exception("Unhandled error during cancellation perform_action")
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=['post'], url_path='sync_wallet_debit')
    def sync_wallet_debit(self, request, pk=None):
        """
        Idempotent repair endpoint: ensures the cancellation wallet debit exists.
        Useful for legacy records that were created without debiting the wallet.
        """
        try:
            cancellation = self.get_object()
            user = request.user

            if not has_workflow_access(user, WORKFLOW_IDS['ENA_CANCELLATION']) and not hasattr(user, 'supply_chain_profile'):
                return Response({'error': 'Unauthorized role for this workflow'}, status=status.HTTP_403_FORBIDDEN)

            fee_amount = self._resolve_cancellation_amount(cancellation)
            refund_amount = self._resolve_permit_refund_amount(cancellation)

            with transaction.atomic():
                wallet_effects = self._apply_wallet_refund_and_fee_for_cancellation_submission(
                    cancellation=cancellation,
                    user=user,
                    refund_amount=refund_amount,
                    fee_amount=fee_amount,
                )

            return Response(
                {
                    'message': 'Wallet debit sync completed.',
                    'wallet_deduction': wallet_effects.get('fee'),
                    'wallet_refund': wallet_effects.get('refund'),
                    'wallet_effects': wallet_effects,
                    'cancellation_ref': getattr(cancellation, 'our_ref_no', ''),
                },
                status=status.HTTP_200_OK,
            )
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.exception("Unhandled error during cancellation sync_wallet_debit")
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

