from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.db import transaction, models, IntegrityError
from django.utils import timezone
from decimal import Decimal
from datetime import timedelta
import logging
from .models import EnaRevalidationDetail
from .serializers import EnaRevalidationDetailSerializer
from models.transactional.supply_chain.ena_requisition_details.models import EnaRequisitionDetail
from models.transactional.supply_chain.ena_requisition_details.models import EnaRevalidationActivationSchedule
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

    def _normalize_token(self, value: str) -> str:
        return ''.join(ch for ch in str(value or '').lower() if ch.isalnum())

    def _looks_final_approved_requisition(self, requisition) -> bool:
        stage = getattr(requisition, 'current_stage', None)
        stage_name = str(getattr(stage, 'name', '') or '') or str(getattr(requisition, 'status', '') or '')
        token = self._normalize_token(stage_name)
        if not token:
            return False
        if 'reject' in token:
            return False
        if 'approv' not in token:
            return False

        if stage is not None and bool(getattr(stage, 'is_final', False)):
            return True

        try:
            from auth.workflow.models import WorkflowTransition
            if stage is not None:
                has_outgoing = WorkflowTransition.objects.filter(from_stage=stage).exists()
                return not has_outgoing
        except Exception:
            pass

        # Fallback: treat as approved if the status text looks approved.
        return True

    def _resolve_revalidation_activation_delay_seconds(self) -> int:
        default_seconds = 10
        try:
            from models.masters.core.models import SupplyChainTimerConfig

            cfg = (
                SupplyChainTimerConfig.objects
                .filter(code='ENA_REVALIDATION_ACTIVATION', is_active=True)
                .order_by('-updated_at', '-id')
                .first()
            )
            if not cfg:
                return default_seconds

            unit = str(getattr(cfg, 'delay_unit', '') or '').lower().strip()
            value = int(getattr(cfg, 'delay_value', 0) or 0)
            if value < 0:
                value = 0

            if unit.endswith('s'):
                unit = unit[:-1]
            unit_aliases = {
                'sec': SupplyChainTimerConfig.TIMER_UNIT_SECOND,
                'secs': SupplyChainTimerConfig.TIMER_UNIT_SECOND,
                'min': SupplyChainTimerConfig.TIMER_UNIT_MINUTE,
                'mins': SupplyChainTimerConfig.TIMER_UNIT_MINUTE,
                'hr': SupplyChainTimerConfig.TIMER_UNIT_HOUR,
                'hrs': SupplyChainTimerConfig.TIMER_UNIT_HOUR,
                'mon': getattr(SupplyChainTimerConfig, 'TIMER_UNIT_MONTH', 'month'),
                'mos': getattr(SupplyChainTimerConfig, 'TIMER_UNIT_MONTH', 'month'),
            }
            unit = unit_aliases.get(unit, unit)

            multipliers = {
                SupplyChainTimerConfig.TIMER_UNIT_SECOND: 1,
                SupplyChainTimerConfig.TIMER_UNIT_MINUTE: 60,
                SupplyChainTimerConfig.TIMER_UNIT_HOUR: 60 * 60,
                SupplyChainTimerConfig.TIMER_UNIT_DAY: 24 * 60 * 60,
                getattr(SupplyChainTimerConfig, 'TIMER_UNIT_MONTH', 'month'): 30 * 24 * 60 * 60,
            }
            multiplier = multipliers.get(unit, 1)
            return max(0, value * multiplier)
        except Exception:
            return default_seconds

    def _find_existing_revalidation_for_requisition(self, requisition):
        details_token = str(getattr(requisition, 'details_permits_number', '') or '').strip()
        license_token = str(getattr(requisition, 'licensee_id', '') or '').strip()

        # IMPORTANT:
        # Do not treat "any revalidation for the same licensee" as a match.
        # That would block creating new revalidations for subsequent requisitions.
        if details_token and license_token:
            return (
                EnaRevalidationDetail.objects
                .filter(licensee_id=license_token, details_permits_number=details_token)
                .order_by('-created_at')
                .first()
            )

        if details_token:
            return (
                EnaRevalidationDetail.objects
                .filter(details_permits_number=details_token)
                .order_by('-created_at')
                .first()
            )

        # If details_permits_number is missing, we can't reliably de-duplicate.
        return None

    def _create_revalidation_from_requisition(self, requisition):
        now = timezone.now()
        license_token = str(getattr(requisition, 'licensee_id', '') or '').strip()
        if not license_token:
            raise ValueError("Requisition is missing licensee_id; cannot auto-create revalidation.")

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
            # EnaRevalidationDetail.branch_address is non-blank; use a safe placeholder if not available.
            'branch_address': (
                str(getattr(requisition, 'via_route', '') or '').strip()
                or str(getattr(requisition, 'check_post_name', '') or '').strip()
                or 'N/A'
            ),
            'branch_purpose': requisition.branch_purpose or requisition.purpose_name or '',
            # EnaRevalidationDetail.govt_officer is non-blank; requisition doesn't store officer name.
            'govt_officer': 'N/A',
            'state': requisition.state or '',
            'revalidation_date': now,
            'status': 'IMPORT PERMIT EXTENDS 45 DAYS INVALID',
            'status_code': 'RV_00',
            'revalidation_br_amount': str(self.REVALIDATION_FEE_AMOUNT),
            'details_permits_number': requisition.details_permits_number or '',
            'distillery_name': requisition.lifted_from_distillery_name or requisition.lifted_from or '',
        }
        payload['licensee_id'] = license_token

        serializer = self.get_serializer(data=payload)
        serializer.is_valid(raise_exception=True)
        return serializer.save()

    def _backfill_missing_activation_schedules(self, scoped_requisitions_qs, now):
        delay_seconds = self._resolve_revalidation_activation_delay_seconds()
        if delay_seconds <= 0:
            return

        # Only backfill rows missing a schedule.
        candidate_qs = scoped_requisitions_qs.filter(
            models.Q(revalidation_activation_schedule__isnull=True)
        ).select_related('current_stage')

        # Reduce scan size using SQL-friendly hints (status_code/stage name),
        # then do the robust check in Python before creating schedules.
        candidate_qs = candidate_qs.filter(
            models.Q(status_code__iexact='RQ_09')
            | models.Q(status__icontains='approv')
            | models.Q(current_stage__name__icontains='approv')
            | models.Q(current_stage__is_final=True)
        )

        for req in candidate_qs.order_by('-updated_at', '-id')[:1000]:
            if not self._looks_final_approved_requisition(req):
                continue
            anchor = (
                getattr(req, 'approval_date', None)
                or getattr(req, 'updated_at', None)
                or getattr(req, 'created_at', None)
                or now
            )
            due_at = anchor + timedelta(seconds=delay_seconds)
            EnaRevalidationActivationSchedule.objects.create(
                requisition=req,
                requisition_ref_no=str(getattr(req, 'our_ref_no', '') or ''),
                approval_date=anchor,
                activation_due_at=due_at,
                status=EnaRevalidationActivationSchedule.STATUS_PENDING,
                notes='Backfilled schedule',
            )

    def _process_due_activation_schedules(self):
        """
        Ensure approved requisitions become visible in the Revalidation tab after the configured delay.

        We avoid requiring a separate background worker by processing due schedules lazily
        when the revalidation list endpoint is called.
        """
        now = timezone.now()
        user = getattr(self.request, 'user', None)

        scoped_reqs = scope_by_profile_or_workflow(
            user,
            EnaRequisitionDetail.objects.filter(updated_at__gte=now - timedelta(days=90)),
            WORKFLOW_IDS['ENA_REQUISITION'],
            licensee_field='licensee_id',
        )
        eligible_req_ids = list(scoped_reqs.values_list('id', flat=True)[:5000])

        # Create missing schedules so older approved requisitions start flowing too.
        try:
            self._backfill_missing_activation_schedules(scoped_reqs, now=now)
        except Exception:
            logger.exception("Unable to backfill activation schedules")

        # Process due pending schedules, and also repair recently-processed schedules
        # that may have been marked processed without actually creating the matching revalidation.
        repair_cutoff = now - timedelta(days=7)
        schedules_qs = (
            EnaRevalidationActivationSchedule.objects
            .select_related('requisition', 'requisition__current_stage')
            .filter(
                activation_due_at__lte=now,
                status__in=[
                    EnaRevalidationActivationSchedule.STATUS_PENDING,
                    EnaRevalidationActivationSchedule.STATUS_PROCESSED,
                ],
            )
            .filter(
                models.Q(status=EnaRevalidationActivationSchedule.STATUS_PENDING)
                | models.Q(activated_at__gte=repair_cutoff)
                | models.Q(updated_at__gte=repair_cutoff)
            )
            .order_by('activation_due_at', 'id')
        )
        if eligible_req_ids:
            schedules_qs = schedules_qs.filter(requisition_id__in=eligible_req_ids)
        else:
            return

        for schedule_id in schedules_qs.values_list('id', flat=True)[:250]:
            try:
                with transaction.atomic():
                    schedule = (
                        EnaRevalidationActivationSchedule.objects
                        .select_for_update()
                        .filter(id=schedule_id)
                        .first()
                    )
                    if not schedule:
                        continue

                    requisition = (
                        EnaRequisitionDetail.objects
                        .select_related('current_stage')
                        .filter(id=schedule.requisition_id)
                        .first()
                    )
                    if requisition is None or not self._looks_final_approved_requisition(requisition):
                        schedule.status = EnaRevalidationActivationSchedule.STATUS_CANCELLED
                        schedule.activated_at = timezone.now()
                        schedule.notes = (schedule.notes or '') + ' Not eligible for activation'
                        schedule.save(update_fields=['status', 'activated_at', 'notes', 'updated_at'])
                        continue

                    if not str(getattr(requisition, 'licensee_id', '') or '').strip():
                        schedule.status = EnaRevalidationActivationSchedule.STATUS_CANCELLED
                        schedule.activated_at = timezone.now()
                        schedule.notes = (schedule.notes or '') + ' Missing requisition.licensee_id'
                        schedule.save(update_fields=['status', 'activated_at', 'notes', 'updated_at'])
                        continue

                    existing = self._find_existing_revalidation_for_requisition(requisition)
                    if existing is None:
                        self._create_revalidation_from_requisition(requisition)

                    schedule.status = EnaRevalidationActivationSchedule.STATUS_PROCESSED
                    schedule.activated_at = timezone.now()
                    schedule.save(update_fields=['status', 'activated_at', 'updated_at'])
            except Exception as exc:
                try:
                    err = "Failed processing activation schedule"
                    logger.exception("%s id=%s", err, schedule_id)
                    schedule = EnaRevalidationActivationSchedule.objects.filter(id=schedule_id).first()
                    if schedule:
                        stamp = timezone.now().isoformat()
                        msg = str(exc).strip()
                        if not msg:
                            msg = repr(exc)
                        detail = f"{type(exc).__name__}: {msg}".strip()
                        if len(detail) > 800:
                            detail = detail[:800] + "..."
                        schedule.notes = (schedule.notes or '').strip()
                        schedule.notes = (schedule.notes + f"\n{stamp} {err} id={schedule_id} {detail}").strip()
                        schedule.save(update_fields=['notes', 'updated_at'])
                except Exception:
                    logger.exception("Failed updating activation schedule notes id=%s", schedule_id)

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
        from models.transactional.wallet.models import WalletBalance, WalletTransaction
        from django.db.models import Q

        try:
            amount = Decimal(
                str(
                    getattr(revalidation, 'revalidation_br_amount', None)
                    or self.REVALIDATION_FEE_AMOUNT
                )
            )
        except Exception:
            amount = self.REVALIDATION_FEE_AMOUNT
        if amount <= 0:
            return {'debited': False, 'reason': 'zero_amount'}

        reference_no = str(getattr(revalidation, 'our_ref_no', '') or f"REV-{revalidation.pk}")
        transaction_id = f"REV-{revalidation.pk}-PAYMENT"

        candidates = self._resolve_wallet_license_candidates(revalidation, user)
        if not candidates:
            raise ValueError("Unable to resolve licensee_id for wallet deduction.")

        # Use transaction_id as the primary idempotency key (licensee_id can be normalized on save).
        already_debited = WalletTransaction.objects.filter(
            transaction_id=transaction_id,
            source_module='ena_revalidation',
            entry_type='DR',
        ).exists()
        if already_debited:
            return {
                'debited': False,
                'reason': 'already_debited',
                'transaction_id': transaction_id,
                'reference_no': reference_no,
            }

        wallet = None
        resolved_licensee_id = ''
        username = str(getattr(user, 'username', '') or '').strip()

        wallet_filter = Q(licensee_id__in=candidates)
        if username:
            wallet_filter |= Q(user_id__iexact=username)

        for cid in candidates:
            wallet = (
                WalletBalance.objects.select_for_update()
                .filter(wallet_filter, wallet_type__iexact='excise')
                .order_by('wallet_balance_id')
                .first()
            )
            if wallet:
                resolved_licensee_id = str(getattr(wallet, 'licensee_id', '') or cid)
                break

        if not wallet:
            for cid in candidates:
                wallet = (
                    WalletBalance.objects.select_for_update()
                    .filter(wallet_filter, wallet_type__iexact='brewery')
                    .order_by('wallet_balance_id')
                    .first()
                )
                if wallet:
                    resolved_licensee_id = str(getattr(wallet, 'licensee_id', '') or cid)
                    break

        if not wallet:
            raise ValueError(
                f"Wallet not found for licensee_id/user_id. Tried licensee_id: {', '.join(candidates)}"
                + (f", user_id={username}" if username else "")
            )

        current_balance = Decimal(str(wallet.current_balance or 0))
        if current_balance < amount:
            raise ValueError(
                f"Insufficient wallet balance. Available: {current_balance}, Required: {amount}"
            )

        now_ts = timezone.now()
        after = current_balance - amount

        # Protect against duplicate-constraint collisions on (transaction_id, head_of_account, entry_type, source_module).
        # Must be checked before applying the debit to avoid double-debit with no transaction row.
        duplicate_txn = WalletTransaction.objects.filter(
            transaction_id=transaction_id,
            head_of_account=wallet.head_of_account,
            entry_type='DR',
            source_module='ena_revalidation'
        ).exists()
        if duplicate_txn:
            return {
                'debited': False,
                'reason': 'already_debited',
                'licensee_id': resolved_licensee_id,
                'transaction_id': transaction_id,
                'reference_no': reference_no,
            }

        sid = transaction.savepoint()
        try:
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
        except IntegrityError:
            transaction.savepoint_rollback(sid)
            return {
                'debited': False,
                'reason': 'already_debited',
                'licensee_id': resolved_licensee_id,
                'transaction_id': transaction_id,
                'reference_no': reference_no,
            }
        else:
            transaction.savepoint_commit(sid)

        return {
            'debited': True,
            'licensee_id': resolved_licensee_id,
            'wallet_type': wallet.wallet_type,
            'amount': str(amount),
            'transaction_id': transaction_id,
            'reference_no': reference_no,
            'balance_before': str(current_balance),
            'balance_after': str(after),
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

    def list(self, request, *args, **kwargs):
        self._process_due_activation_schedules()
        return super().list(request, *args, **kwargs)

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

        # Same rationale as schedule processor: avoid licensee-only matches.
        if license_token and details_token:
            existing = EnaRevalidationDetail.objects.filter(
                licensee_id=license_token,
                details_permits_number=details_token,
            ).order_by('-created_at').first()

        if existing is None and details_token:
            existing = EnaRevalidationDetail.objects.filter(
                details_permits_number=details_token
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
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

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
