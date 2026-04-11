from rest_framework import serializers
from django.db import transaction, models
from decimal import Decimal, InvalidOperation, ROUND_DOWN, ROUND_HALF_UP
from django.core.exceptions import ObjectDoesNotExist
from django.db.utils import ProgrammingError, OperationalError
from django.contrib.contenttypes.models import ContentType
from .models import EnaRequisitionDetail, RequisitionBulkLiterDetail, RequisitionBulkLiterReviewAudit
from auth.workflow.constants import WORKFLOW_IDS
from auth.workflow.models import Rejection
from models.masters.license.models import License
import logging
import re
from models.transactional.supply_chain.access_control import condition_role_matches

logger = logging.getLogger(__name__)

class EnaRequisitionDetailSerializer(serializers.ModelSerializer):
    allowed_actions = serializers.SerializerMethodField()
    allowed_action_configs = serializers.SerializerMethodField()
    can_initiate_cancellation = serializers.SerializerMethodField()
    has_active_revalidation = serializers.SerializerMethodField()
    establishment_name = serializers.SerializerMethodField()
    rejected_by_display = serializers.SerializerMethodField()
    cancellation_reason_display = serializers.SerializerMethodField()
    
    current_stage_name = serializers.CharField(source='current_stage.name', read_only=True)
    current_stage_is_final = serializers.SerializerMethodField()
    workflow_name = serializers.CharField(source='workflow.name', read_only=True)
    
    # Explicitly include our_ref_no to ensure it's serialized
    our_ref_no = serializers.CharField(read_only=True)

    class Meta:
        model = EnaRequisitionDetail
        fields = '__all__'
        extra_kwargs = {
            'status': {'required': False},
            'status_code': {'required': False},
            'our_ref_no': {'required': False},  # Auto-generated
        }
        
    def to_representation(self, instance):
        """Override to ensure all fields are always included"""
        data = super().to_representation(instance)
        
        # Explicitly ensure critical fields are included with proper values
        data['our_ref_no'] = instance.our_ref_no or ''
        data['lifted_from'] = instance.lifted_from or ''
        data['via_route'] = instance.via_route or ''
        data['check_post_name'] = instance.check_post_name or ''
        data['branch_purpose'] = instance.branch_purpose or ''
        data['lifted_from_distillery_name'] = instance.lifted_from_distillery_name or ''
        data['purpose_name'] = instance.purpose_name or ''
        data['totalbl'] = str(instance.totalbl) if instance.totalbl else '0'
        data['payment_amount'] = str(
            self._resolve_payment_amount_from_values(
                total_bl_raw=instance.totalbl,
                spirit_kind=instance.bulk_spirit_type,
                strength=instance.strength
            )
        )
        data['grain_ena_number'] = str(instance.grain_ena_number) if instance.grain_ena_number else '0'
        data['requisiton_number_of_permits'] = instance.requisiton_number_of_permits or 1
        data['details_permits_number'] = instance.details_permits_number or ''
        data['bulk_spirit_type'] = instance.bulk_spirit_type or ''
        data['strength'] = instance.strength or ''
        data['status'] = instance.status or 'PENDING'
        # Arrival details summary (permit-wise partial approvals supported)
        try:
            details_qs = RequisitionBulkLiterDetail.objects.filter(requisition=instance).order_by('-updated_at')
        except Exception:
            details_qs = RequisitionBulkLiterDetail.objects.none()

        if details_qs.exists():
            data['has_arrival_details'] = True

            # Determine total permits for the requisition.
            permit_tokens = [
                str(token).strip()
                for token in str(getattr(instance, 'details_permits_number', '') or '').split(',')
                if str(token).strip()
            ]
            if not permit_tokens:
                try:
                    count = int(getattr(instance, 'requisiton_number_of_permits', 0) or 0)
                except (TypeError, ValueError):
                    count = 0
                count = max(0, count)
                permit_tokens = [str(i) for i in range(1, count + 1)] if count > 0 else []
            total_permits = len(permit_tokens)

            cancelled_permits_approved = set()
            try:
                cancelled_permits_approved = set(self._approved_cancelled_permit_numbers_for_requisition(getattr(instance, 'our_ref_no', '') or ''))
            except Exception:
                cancelled_permits_approved = set()

            cancel_requested_permits = set()
            try:
                cancel_requested_permits = set(self._cancellation_requested_permit_numbers_for_requisition(getattr(instance, 'our_ref_no', '') or ''))
            except Exception:
                cancel_requested_permits = set()

            cancelled_permits = set(cancelled_permits_approved or set()).union(set(cancel_requested_permits or set()))
            if permit_tokens:
                permitted = set(permit_tokens)
                cancelled_permits_approved = {token for token in cancelled_permits_approved if token in permitted}
                cancel_requested_permits = {token for token in cancel_requested_permits if token in permitted}
                cancelled_permits = {token for token in cancelled_permits if token in permitted}

            approved_details = details_qs.filter(approval_status=RequisitionBulkLiterDetail.ApprovalStatus.APPROVED)
            pending_details = details_qs.filter(approval_status=RequisitionBulkLiterDetail.ApprovalStatus.PENDING)
            rejected_details = details_qs.filter(approval_status=RequisitionBulkLiterDetail.ApprovalStatus.REJECTED)

            def _permits_in_detail(detail_row):
                tanker_rows = detail_row.tanker_details or []
                tokens = [
                    str(item.get('permit_no') or '').strip()
                    for item in tanker_rows
                    if isinstance(item, dict) and str(item.get('permit_no') or '').strip()
                ]
                if tokens:
                    return set(tokens)
                if total_permits and isinstance(tanker_rows, list) and len(tanker_rows) == total_permits:
                    return set(permit_tokens)
                return set()

            def _merge_status(existing_status: str, next_status: str) -> str:
                order = {'APPROVED': 3, 'PENDING': 2, 'REJECTED': 1, '': 0}
                a = str(existing_status or '').upper()
                b = str(next_status or '').upper()
                return b if order.get(b, 0) >= order.get(a, 0) else a

            # Compute effective/latest status per permit (APPROVED > PENDING > REJECTED).
            permit_status_by_permit = {}
            for row in details_qs:
                status_token = str(getattr(row, 'approval_status', '') or '').upper()
                for token in _permits_in_detail(row):
                    if token in cancelled_permits:
                        continue
                    permit_status_by_permit[token] = _merge_status(permit_status_by_permit.get(token, ''), status_token)

            approved_permits = {p for p, s in permit_status_by_permit.items() if str(s).upper() == 'APPROVED'}
            pending_permits = {p for p, s in permit_status_by_permit.items() if str(s).upper() == 'PENDING'}
            rejected_permits = {p for p, s in permit_status_by_permit.items() if str(s).upper() == 'REJECTED'}

            # Remaining permits are those not approved/pending (rejected permits count as remaining to be re-submitted).
            remaining_permits = max(0, total_permits - len(approved_permits) - len(pending_permits) - len(cancelled_permits))

            approved_total = Decimal('0')
            approved_tanker_count = 0
            for row in approved_details:
                try:
                    approved_total += Decimal(str(row.total_bulk_liter or '0'))
                except Exception:
                    pass
                try:
                    approved_tanker_count += int(row.tanker_count or 0)
                except Exception:
                    pass

            pending_total = Decimal('0')
            pending_tanker_count = 0
            for row in pending_details:
                try:
                    pending_total += Decimal(str(row.total_bulk_liter or '0'))
                except Exception:
                    pass
                try:
                    pending_tanker_count += int(row.tanker_count or 0)
                except Exception:
                    pass

            latest_row = details_qs.first()
            # Inventory total should include APPROVED + PENDING (exclude rejected).
            inventory_total = (approved_total + pending_total)
            inventory_tankers = (approved_tanker_count + pending_tanker_count)
            data['arrival_total_bulk_liter'] = str(inventory_total or '0')
            data['arrival_tanker_count'] = int(inventory_tankers or 0)
            data['arrival_total_permits_count'] = total_permits
            data['arrival_approved_permits_count'] = len(approved_permits)
            data['arrival_pending_permits_count'] = len(pending_permits)
            data['arrival_rejected_permits_count'] = len(rejected_permits)
            data['arrival_cancelled_permits_count'] = len(cancelled_permits)
            data['arrival_remaining_permits_count'] = remaining_permits
            data['arrival_submitted_at'] = latest_row.submitted_at.isoformat() if latest_row and latest_row.submitted_at else None
            data['arrival_reviewed_at'] = latest_row.reviewed_at.isoformat() if latest_row and latest_row.reviewed_at else None
            data['arrival_reviewed_by'] = latest_row.reviewed_by or '' if latest_row else ''
            data['arrival_review_remarks'] = latest_row.review_remarks or '' if latest_row else ''

            if pending_permits:
                data['arrival_approval_status'] = 'PENDING'
            elif total_permits > 0 and (len(approved_permits) + len(cancelled_permits_approved)) == total_permits:
                data['arrival_approval_status'] = 'APPROVED'
            elif total_permits > 0 and remaining_permits == 0 and len(cancel_requested_permits) > 0:
                data['arrival_approval_status'] = 'PARTIAL'
            elif len(approved_permits) > 0 and remaining_permits > 0:
                data['arrival_approval_status'] = 'PARTIAL'
            elif len(rejected_permits) > 0 and len(approved_permits) == 0:
                data['arrival_approval_status'] = 'REJECTED'
            else:
                data['arrival_approval_status'] = 'PENDING'
        else:
            data['has_arrival_details'] = False
            data['arrival_total_bulk_liter'] = '0'
            data['arrival_tanker_count'] = 0
            data['arrival_approval_status'] = ''

            permit_tokens = [
                str(token).strip()
                for token in str(getattr(instance, 'details_permits_number', '') or '').split(',')
                if str(token).strip()
            ]
            if not permit_tokens:
                try:
                    count = int(getattr(instance, 'requisiton_number_of_permits', 0) or 0)
                except (TypeError, ValueError):
                    count = 0
                count = max(0, count)
                permit_tokens = [str(i) for i in range(1, count + 1)] if count > 0 else []
            total_permits = len(permit_tokens)

            cancelled_permits_approved = set()
            try:
                cancelled_permits_approved = set(self._approved_cancelled_permit_numbers_for_requisition(getattr(instance, 'our_ref_no', '') or ''))
            except Exception:
                cancelled_permits_approved = set()

            cancel_requested_permits = set()
            try:
                cancel_requested_permits = set(self._cancellation_requested_permit_numbers_for_requisition(getattr(instance, 'our_ref_no', '') or ''))
            except Exception:
                cancel_requested_permits = set()

            cancelled_permits = set(cancelled_permits_approved or set()).union(set(cancel_requested_permits or set()))
            if permit_tokens:
                permitted = set(permit_tokens)
                cancelled_permits_approved = {token for token in cancelled_permits_approved if token in permitted}
                cancel_requested_permits = {token for token in cancel_requested_permits if token in permitted}
                cancelled_permits = {token for token in cancelled_permits if token in permitted}

            remaining = max(0, total_permits - len(cancelled_permits))

            data['arrival_total_permits_count'] = total_permits
            data['arrival_approved_permits_count'] = 0
            data['arrival_pending_permits_count'] = 0
            data['arrival_rejected_permits_count'] = 0
            data['arrival_cancelled_permits_count'] = len(cancelled_permits)
            data['arrival_remaining_permits_count'] = remaining
            data['arrival_submitted_at'] = None
            data['arrival_reviewed_at'] = None
            data['arrival_reviewed_by'] = ''
            data['arrival_review_remarks'] = ''
            try:
                audit = instance.bulk_liter_review_audit
                data['arrival_approval_status'] = audit.last_status or ''
                data['arrival_reviewed_at'] = audit.reviewed_at.isoformat() if audit.reviewed_at else None
                data['arrival_reviewed_by'] = audit.reviewed_by or ''
                data['arrival_review_remarks'] = audit.review_remarks or ''
            except (ObjectDoesNotExist, ProgrammingError, OperationalError):
                pass
        
        # Ensure status_code is set - derive from stage if not set
        if not instance.status_code or instance.status_code == 'RQ_00':
            data['status_code'] = self._derive_status_code_from_stage(instance)
        else:
            data['status_code'] = instance.status_code
        
        return data

    def _expand_license_aliases(self, raw_license_id):
        token = str(raw_license_id or '').strip()
        if not token:
            return []

        aliases = [token]
        if token.startswith('NLI/'):
            aliases.append(f"NA/{token[4:]}")
        elif token.startswith('NA/'):
            aliases.append(f"NLI/{token[3:]}")
        return aliases

    def get_establishment_name(self, obj):
        for license_id in self._expand_license_aliases(getattr(obj, 'licensee_id', '')):
            license_obj = (
                License.objects.filter(license_id__iexact=license_id)
                .select_related('source_content_type')
                .first()
            )
            if not license_obj:
                continue

            source = getattr(license_obj, 'source_application', None)
            if not source:
                continue

            establishment_name = str(getattr(source, 'establishment_name', '') or '').strip()
            if establishment_name:
                return establishment_name

            company_name = str(getattr(source, 'company_name', '') or '').strip()
            if company_name:
                return company_name

        return ''

    def get_rejected_by_display(self, obj):
        """Return role label of the latest rejecting officer (e.g., Permit Section/Commissioner)."""
        stored_role = str(getattr(obj, 'rejected_by_role', '') or '').strip()
        if stored_role:
            return self._humanize_role_name(stored_role)

        try:
            content_type = ContentType.objects.get_for_model(obj.__class__)
            latest_rejection = (
                Rejection.objects.filter(content_type=content_type, object_id=str(obj.pk))
                .select_related('rejected_by__role')
                .order_by('-rejected_on')
                .first()
            )
            if latest_rejection:
                role_name = str(getattr(getattr(latest_rejection.rejected_by, 'role', None), 'name', '') or '').strip()
                if role_name:
                    return self._humanize_role_name(role_name)

                full_name = str(getattr(latest_rejection.rejected_by, 'full_name', '') or '').strip()
                if full_name:
                    return full_name

                username = str(getattr(latest_rejection.rejected_by, 'username', '') or '').strip()
                if username:
                    return username
        except Exception:
            pass

        # Fallback: requisition reject flow uses WorkflowService.advance_stage(),
        # which always writes a Transaction with performed_by/forwarded_by role.
        try:
            latest_txn = (
                obj.transactions.select_related('performed_by__role', 'forwarded_by', 'stage')
                .order_by('-timestamp')
                .first()
            )
            if not latest_txn:
                return ''

            role_name = str(getattr(getattr(latest_txn, 'forwarded_by', None), 'name', '') or '').strip()
            if role_name:
                return self._humanize_role_name(role_name)

            actor_role = str(getattr(getattr(getattr(latest_txn, 'performed_by', None), 'role', None), 'name', '') or '').strip()
            if actor_role:
                return self._humanize_role_name(actor_role)

            stage_name = str(getattr(getattr(latest_txn, 'stage', None), 'name', '') or '').strip()
            stage_hint = self._role_from_stage_name(stage_name)
            if stage_hint:
                return stage_hint
        except Exception:
            return ''

        return ''

    def get_cancellation_reason_display(self, obj):
        stored_reason = str(getattr(obj, 'cancellation_reason', '') or '').strip()
        if stored_reason:
            return stored_reason

        # Fallback for historical rows where reason may only exist in workflow rejection remarks.
        try:
            content_type = ContentType.objects.get_for_model(obj.__class__)
            latest_rejection = (
                Rejection.objects.filter(content_type=content_type, object_id=str(obj.pk))
                .order_by('-rejected_on')
                .values_list('remarks', flat=True)
                .first()
            )
            rejection_reason = str(latest_rejection or '').strip()
            if rejection_reason:
                return rejection_reason

            latest_txn_remarks = (
                obj.transactions.order_by('-timestamp')
                .values_list('remarks', flat=True)
                .first()
            )
            txn_reason = str(latest_txn_remarks or '').strip()
            if txn_reason and txn_reason.lower() not in {'action: reject', 'reject'}:
                return txn_reason
            return ''
        except Exception:
            return ''

    def _role_from_stage_name(self, value):
        token = str(value or '').lower()
        if 'permit' in token and 'section' in token:
            return 'Permit Section'
        if 'commissioner' in token:
            return 'Commissioner'
        return ''

    def _humanize_role_name(self, value):
        normalized = str(value or '').replace('_', ' ').replace('-', ' ').strip()
        if not normalized:
            return ''
        return ' '.join(part.capitalize() for part in normalized.split())
    
    def _derive_status_code_from_stage(self, instance):
        """
        Derive status_code from current_stage or status field.
        This is a fallback for when status_code is not properly set.
        """
        stage_name = ''
        if instance.current_stage:
            stage_name = instance.current_stage.name
            # Check if stage is final (approved)
            if getattr(instance.current_stage, 'is_final', False):
                # Check if it's approved or rejected
                stage_lower = stage_name.lower()
                if 'reject' in stage_lower:
                    return 'RQ_10'  # Rejected
                else:
                    return 'RQ_09'  # Approved
        else:
            stage_name = instance.status or ''
        
        # Infer status code from stage semantics (robust to stage label renames).
        stage_lower = self._normalize_stage_token(stage_name)

        if 'reject' in stage_lower:
            return 'RQ_10'
        if 'approv' in stage_lower:
            return 'RQ_09'
        if 'forward' in stage_lower and 'payslip' in stage_lower and 'permitsection' in stage_lower:
            return 'RQ_04'
        if 'forward' in stage_lower and 'permitsection' in stage_lower:
            return 'RQ_03'
        if 'forward' in stage_lower and 'commissioner' in stage_lower:
            return 'RQ_06'
        if 'review' in stage_lower:
            return 'RQ_02'
        if 'submit' in stage_lower:
            return 'RQ_01'
        if 'pending' in stage_lower:
            return 'RQ_00'

        return instance.status_code or 'RQ_00'

    def get_allowed_actions(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return []

        # CustomUser uses 'role' field, not 'groups'
        # Check if user has a role and get its name
        user_role_name = request.user.role.name if hasattr(request.user, 'role') and request.user.role else None
        
        if not user_role_name:
            return []
        
        # Normalize role name
        user_role_name = str(user_role_name).strip()
        cleaned_role_name = user_role_name.lower()
        
        # Determine Role (Matching Frontend Logic)
        role = None
        
        # Commissioner roles (add more aliases if needed)
        if cleaned_role_name in ['commissioner', 'level_1', 'level_2', 'level_3', 'level_4', 'level_5', 'site_admin', 'site-admin']:
            role = 'commissioner'
        # Permit Section roles
        elif cleaned_role_name in ['permit-section', 'permit section', 'permit_section']:
            role = 'permit-section'
        # Licensee roles
        elif cleaned_role_name in ['licensee', 'license user', 'license_user']:
            role = 'licensee'
        
        if not role:
            # Fallback for simple exact matches if not caught above
            role = cleaned_role_name
        
        # Query Workflow Transitions
        from auth.workflow.models import WorkflowTransition
        
        current_stage = obj.current_stage
        if not current_stage:
            current_stage = self._resolve_stage_for_object(obj)
            if not current_stage:
                return []

        transitions = WorkflowTransition.objects.filter(from_stage=current_stage).select_related('to_stage')
        actions = []
        for t in transitions:
            cond = t.condition or {}
            if not condition_role_matches(cond, request.user):
                continue

            action = cond.get('action')
            if action:
                normalized_action = self._normalize_ui_action_name(
                    action_name=action,
                    transition=t,
                    current_stage=current_stage,
                    role=role
                )
                if self._should_expose_action(
                    action_name=normalized_action,
                    role=role,
                    current_stage=current_stage
                ):
                    actions.append(normalized_action)
        
        return list(set(actions)) # Unique actions

    def get_current_stage_is_final(self, obj):
        stage = getattr(obj, 'current_stage', None)
        if not stage:
            return False

        if bool(getattr(stage, 'is_final', False)):
            return True

        from auth.workflow.models import WorkflowTransition
        has_outgoing = WorkflowTransition.objects.filter(from_stage=stage).exists()
        return not has_outgoing

    def _normalize_stage_token(self, value):
        token = ''.join(ch for ch in str(value or '').lower() if ch.isalnum())
        return token

    def _resolve_stage_for_object(self, obj):
        from auth.workflow.models import WorkflowStage

        workflow_id = getattr(obj, 'workflow_id', None) or WORKFLOW_IDS['ENA_REQUISITION']
        stages = list(WorkflowStage.objects.filter(workflow_id=workflow_id))
        if not stages:
            return None

        hint = self._normalize_stage_token(getattr(obj, 'status', ''))
        if hint:
            for stage in stages:
                if self._normalize_stage_token(stage.name) == hint:
                    return stage

            keywords = [
                key for key in ['pending', 'submit', 'review', 'forward', 'permitsection', 'commissioner', 'payslip', 'approve', 'reject']
                if key in hint
            ]
            if keywords:
                scored = []
                for stage in stages:
                    stage_token = self._normalize_stage_token(stage.name)
                    score = sum(1 for key in keywords if key in stage_token)
                    scored.append((score, stage))
                best_score, best_stage = max(scored, key=lambda item: item[0])
                if best_score > 0:
                    return best_stage

        initial = next((stage for stage in stages if getattr(stage, 'is_initial', False)), None)
        return initial or stages[0]

    def _looks_like_payment_stage(self, value):
        token = self._normalize_stage_token(value)
        payment_markers = ['pay', 'payment', 'payslip', 'wallet', 'fee']
        return any(marker in token for marker in payment_markers)

    def _normalize_ui_action_name(self, action_name, transition=None, current_stage=None, role=None):
        normalized = str(action_name or '').strip().upper()
        if normalized != 'APPROVE':
            return normalized

        # Only licensee-facing transitions can be represented as PAY in UI.
        if str(role or '').lower() != 'licensee':
            return normalized

        current_name = getattr(current_stage, 'name', '')
        to_name = getattr(getattr(transition, 'to_stage', None), 'name', '')
        if self._looks_like_payment_stage(current_name) or self._looks_like_payment_stage(to_name):
            return 'PAY'

        return normalized

    def _is_post_payment_stage(self, stage_name):
        token = self._normalize_stage_token(stage_name)
        post_payment_markers = [
            'forwardedpayslip',
            'permitsection',
            'approvedpayslip',
            'rejectedpayslip',
            'paymentsuccess',
            'paid',
            'paymentcompleted',
        ]
        return any(marker in token for marker in post_payment_markers)

    def _should_expose_action(self, action_name, role, current_stage=None):
        normalized_action = str(action_name or '').strip().upper()
        normalized_role = str(role or '').strip().lower()
        current_stage_name = getattr(current_stage, 'name', '')

        # PAY should be shown only to licensee and only before payment completion.
        if normalized_action == 'PAY':
            if normalized_role != 'licensee':
                return False
            if self._is_post_payment_stage(current_stage_name):
                return False
            return True

        return True

    # New Field: Returns Full UI Config for Actions
    allowed_action_configs = serializers.SerializerMethodField()

    def get_allowed_action_configs(self, obj):
        # 1. Get standard workflow actions
        actions = self.get_allowed_actions(obj)
        
        # 2. Check for "Request Cancellation" specific logic
        # This is independent of workflow transitions since it's a special action
        # that can be initiated from a final approved stage
        if self.get_can_initiate_cancellation(obj):
            if 'REQUEST_CANCELLATION' not in actions:
                actions.append('REQUEST_CANCELLATION')
        
        # 3. If no actions at all, return empty list
        if not actions:
            return []
        
        # 4. Convert action names to UI configs
        from auth.workflow.services import WorkflowService
        configs = []
        for action_name in actions:
            try:
                config = WorkflowService.get_action_config(action_name)
                if config:
                    configs.append(config)
            except Exception as e:
                logger.exception("Error getting UI config for action=%s", action_name)
                # Add a basic config as fallback
                configs.append({
                    'action': action_name,
                    'label': action_name.replace('_', ' ').title(),
                    'icon': 'arrow_forward',
                    'color': 'primary',
                    'tooltip': action_name.replace('_', ' ').title()
                })
        
        return configs

    def get_can_initiate_cancellation(self, obj):
        request = self.context.get('request')

        if not request or not request.user.is_authenticated:
            return False
            
        # Only Licensee can initiate cancellation
        user_role_name = request.user.role.name if hasattr(request.user, 'role') and request.user.role else None

        if user_role_name not in ['licensee', 'Licensee']:
            return False

        status_lower = str(obj.status or '').lower()
        stage_name_lower = str(obj.current_stage.name or '').lower() if obj.current_stage else ''
        status_code = str(getattr(obj, 'status_code', '') or '').upper()

        current_stage_name = obj.current_stage.name if obj.current_stage else 'None'
        is_final_stage = getattr(obj.current_stage, 'is_final', False) if obj.current_stage else False
        combined = f"{status_lower} {stage_name_lower}"
        looks_approved = ('approv' in combined) and ('reject' not in combined)
        # Cancellation request should be allowed only at approved requisition stage.
        # Prefer workflow final flag, but fall back to status/stage tokens when legacy data lacks is_final.
        is_final_approved = looks_approved and (
            is_final_stage or
            ('commissioner' in combined) or
            ('approved' in combined) or
            ('approv' in combined)
        )

        if not is_final_approved:
            return False
        
        # Check if it's approved (not rejected)
        
        # If status or stage name contains 'reject', it's not approved
        if 'reject' in status_lower or 'reject' in stage_name_lower:
            return False
        
        # Check if there's an active revalidation - if yes, cannot cancel
        has_active_reval = self.get_has_active_revalidation(obj)

        if has_active_reval:
            return False

        # Check if all requisition permits are already cancelled by commissioner-approved cancellations
        if self._are_all_requisition_permits_cancelled(obj):
            return False
        
        # Check if already cancelled or cancellation in progress
        if 'cancel' in status_lower or 'cancel' in stage_name_lower:
            return False
        
        return True

    def _parse_permit_tokens(self, value):
        return [
            str(token).strip()
            for token in str(value or '').split(',')
            if str(token).strip()
        ]

    def _is_commissioner_approved_cancellation(self, cancellation_obj):
        status_token = self._normalize_stage_token(getattr(cancellation_obj, 'status', ''))
        stage_name = ''
        if getattr(cancellation_obj, 'current_stage', None):
            stage_name = getattr(cancellation_obj.current_stage, 'name', '')
        stage_token = self._normalize_stage_token(stage_name)

        merged = f"{status_token} {stage_token}"
        return 'approved' in merged and 'commissioner' in merged

    def _is_rejected_cancellation(self, cancellation_obj) -> bool:
        status_token = self._normalize_stage_token(getattr(cancellation_obj, 'status', ''))
        stage_name = ''
        if getattr(cancellation_obj, 'current_stage', None):
            stage_name = getattr(cancellation_obj.current_stage, 'name', '')
        stage_token = self._normalize_stage_token(stage_name)

        merged = f"{status_token} {stage_token}"
        return 'reject' in merged

    def _approved_cancelled_permit_numbers_for_requisition(self, requisition_ref_no):
        if not requisition_ref_no:
            return set()

        from models.transactional.supply_chain.ena_cancellation_details.models import EnaCancellationDetail

        rows = EnaCancellationDetail.objects.filter(
            models.Q(requisition_ref_no=requisition_ref_no) |
            models.Q(our_ref_no=requisition_ref_no)
        ).select_related('current_stage')

        approved_numbers = set()
        for row in rows:
            if not self._is_commissioner_approved_cancellation(row):
                continue
            cancelled_raw = getattr(row, 'cancelled_permit_numbers', None) or getattr(row, 'cancelled_permit_number', None) or ''
            for token in self._parse_permit_tokens(cancelled_raw):
                approved_numbers.add(token)

        return approved_numbers

    def _cancellation_requested_permit_numbers_for_requisition(self, requisition_ref_no):
        if not requisition_ref_no:
            return set()

        from models.transactional.supply_chain.ena_cancellation_details.models import EnaCancellationDetail

        rows = EnaCancellationDetail.objects.filter(
            models.Q(requisition_ref_no=requisition_ref_no) |
            models.Q(our_ref_no=requisition_ref_no)
        ).select_related('current_stage')

        requested_numbers = set()
        for row in rows:
            if self._is_rejected_cancellation(row):
                continue
            if self._is_commissioner_approved_cancellation(row):
                continue
            cancelled_raw = getattr(row, 'cancelled_permit_numbers', None) or getattr(row, 'cancelled_permit_number', None) or ''
            for token in self._parse_permit_tokens(cancelled_raw):
                requested_numbers.add(token)

        return requested_numbers

    def _all_requisition_permit_numbers(self, obj):
        permit_tokens = self._parse_permit_tokens(getattr(obj, 'details_permits_number', ''))
        if permit_tokens:
            return set(permit_tokens)

        count = self._safe_permit_count(getattr(obj, 'requisiton_number_of_permits', 0))
        return {str(i) for i in range(1, count + 1)}

    def _are_all_requisition_permits_cancelled(self, obj):
        all_permits = self._all_requisition_permit_numbers(obj)
        if not all_permits:
            return False
        approved_cancelled = self._approved_cancelled_permit_numbers_for_requisition(getattr(obj, 'our_ref_no', ''))
        return all_permits.issubset(approved_cancelled)

    def get_has_active_revalidation(self, obj):
        """
        Check if there's an active (in-progress) revalidation for this requisition.
        A revalidation is considered active if it's not in a final/completed state.
        """
        try:
            from models.transactional.supply_chain.ena_revalidation_details.models import EnaRevalidationDetail
            
            # Check for revalidations with the same licensee_id and similar reference pattern
            # or created recently (within last 90 days) for the same licensee
            from django.utils import timezone
            from datetime import timedelta
            
            ninety_days_ago = timezone.now() - timedelta(days=90)

            licensee_id = str(getattr(obj, 'licensee_id', '') or '').strip()
            details_token = str(getattr(obj, 'details_permits_number', '') or '').strip()

            # Look for revalidations that:
            # 1. Belong to the same licensee (preferred)
            # 2. Or match permit number batch when licensee is missing
            # 3. Were created recently (within 90 days)
            # 4. Are not in a final/completed state (status_code not ending in approved/rejected/cancelled)
            base_qs = EnaRevalidationDetail.objects.filter(created_at__gte=ninety_days_ago)
            if licensee_id:
                base_qs = base_qs.filter(licensee_id=licensee_id)
            elif details_token:
                base_qs = base_qs.filter(details_permits_number=details_token)
            else:
                return False

            active_revalidations = base_qs.exclude(
                status_code__in=['RV_09', 'RV_APPROVED', 'RV_REJECTED', 'RV_CANCELLED']
            ).exclude(
                status__icontains='cancelled'
            ).exclude(
                status__icontains='rejected'
            )
            
            # Additional check: if current_stage.is_final is True, it's not active
            active_count = 0
            for revalidation in active_revalidations:
                if revalidation.current_stage and getattr(revalidation.current_stage, 'is_final', False):
                    continue
                active_count += 1
            
            return active_count > 0
            
        except Exception as e:
            logger.exception("Error checking active revalidation for requisition=%s", getattr(obj, "id", None))
            return False

    def create(self, validated_data):
        # from models.masters.supply_chain.status_master.models import StatusMaster # Removed
        
        # Auto-generate reference number
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
        validated_data['our_ref_no'] = f"REQ/{next_number:02d}/EXCISE"
        
        # Prefer explicit request value (license format like NA/....)
        request = self.context.get('request')
        if request:
            requested_licensee_id = request.data.get('licensee_id') or request.data.get('licenseeId')
            if requested_licensee_id:
                validated_data['licensee_id'] = requested_licensee_id

        # Fallback: Auto-populate Licensee ID from Profile
        if not validated_data.get('licensee_id') and request and request.user and hasattr(request.user, 'supply_chain_profile'):
            validated_data['licensee_id'] = request.user.supply_chain_profile.licensee_id
        elif request and request.user and hasattr(request.user, 'manufacturing_units'):
            # Fallback to first mapped unit if active profile is not set.
            unit = request.user.manufacturing_units.exclude(licensee_id__isnull=True).exclude(licensee_id='').first()
            if unit:
                validated_data['licensee_id'] = unit.licensee_id

        if not validated_data.get('licensee_id'):
            raise serializers.ValidationError({
                'licensee_id': 'Unable to determine licensee mapping. Please set your active supply-chain profile and try again.'
            })
        
        # Initialize Workflow and Status
        from auth.workflow.models import Workflow, WorkflowStage
        try:
            workflow = Workflow.objects.get(id=WORKFLOW_IDS['ENA_REQUISITION'])
            initial_stage = WorkflowStage.objects.get(workflow=workflow, is_initial=True)
            
            validated_data['workflow'] = workflow
            validated_data['current_stage'] = initial_stage
            
            # Use stage name for status, and default 'RQ_00' for status_code
            validated_data['status'] = initial_stage.name
            validated_data['status_code'] = 'RQ_00'
            
        except Exception as e:
            # Fallback for robustness
            logger.exception("Workflow initialization failed for ENA requisition")
            validated_data['status'] = 'Pending'
            validated_data['status_code'] = 'RQ_00'

        # Store running permit numbers sequence (e.g. "1,2,3" then "4,5,6,7").
        permit_count = self._safe_permit_count(validated_data.get('requisiton_number_of_permits'))
        validated_data['details_permits_number'] = self._build_details_permit_numbers(permit_count)
            
        return super().create(validated_data)

    def _safe_permit_count(self, value) -> int:
        try:
            count = int(value or 0)
        except (TypeError, ValueError):
            return 0
        return max(0, count)

    def _parse_last_permit_number(self, sequence_text: str) -> int:
        tokens = [str(part).strip() for part in str(sequence_text or '').split(',')]
        numbers = []
        for token in tokens:
            if token.isdigit():
                numbers.append(int(token))
        return max(numbers) if numbers else 0

    def _build_details_permit_numbers(self, permit_count: int) -> str:
        if permit_count <= 0:
            return ''

        with transaction.atomic():
            last_row = (
                EnaRequisitionDetail.objects
                .select_for_update()
                .order_by('-id')
                .first()
            )
            last_end = self._parse_last_permit_number(
                getattr(last_row, 'details_permits_number', '') if last_row else ''
            )
            start = last_end + 1
            end = start + permit_count - 1
            return ','.join(str(num) for num in range(start, end + 1))

    def _resolve_payment_amount_from_values(self, total_bl_raw, spirit_kind, strength='') -> float:
        # Backend computation: selected bulk spirit price_bl * total BL.
        try:
            total_bl = float(total_bl_raw)
        except (TypeError, ValueError):
            total_bl = 0.0
        if total_bl <= 0:
            return 0.0

        spirit_kind = str(spirit_kind or '').strip()
        strength = str(strength or '').strip()
        if not spirit_kind:
            return 0.0

        try:
            from models.masters.supply_chain.bulk_spirit.models import BulkSpiritType
            qs = BulkSpiritType.objects.filter(
                bulk_spirit_kind_type__iexact=spirit_kind
            )
            if strength:
                qs = qs.filter(strength__iexact=strength)
            row = qs.order_by('sprit_id').first()
            if row and row.price_bl is not None:
                return float(row.price_bl) * total_bl
        except Exception:
            pass

        return 0.0


class RequisitionBulkLiterDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = RequisitionBulkLiterDetail
        fields = '__all__'
        read_only_fields = [
            'reference_no',
            'licensee_id',
            'total_bulk_liter',
            'approval_status',
            'submitted_at',
            'reviewed_at',
            'reviewed_by',
            'review_remarks',
            'edited_by_oic',
            'edited_at',
            'edited_by',
            'created_at',
            'updated_at'
        ]

    def validate(self, attrs):
        tanker_details = attrs.get('tanker_details')
        tanker_count = attrs.get('tanker_count')

        if tanker_details is None and self.instance is not None:
            tanker_details = self.instance.tanker_details
        if tanker_count is None and self.instance is not None:
            tanker_count = self.instance.tanker_count

        tanker_count = int(tanker_count or 0)
        if tanker_count <= 0:
            raise serializers.ValidationError({'tanker_count': 'Tanker count must be greater than 0.'})

        if not isinstance(tanker_details, list):
            raise serializers.ValidationError({'tanker_details': 'Tanker details must be a list.'})

        if len(tanker_details) != tanker_count:
            raise serializers.ValidationError({
                'tanker_details': 'Tanker details count must match tanker_count.'
            })

        normalized_rows = []
        total_bulk_liter = Decimal('0')

        expected_by_permit = {}
        requisition = attrs.get('requisition') or getattr(self.instance, 'requisition', None)
        requested_total_bl = Decimal('0')
        permit_tokens = []
        permit_count = 0
        if requisition is not None:
            try:
                requested_total_bl = Decimal(str(getattr(requisition, 'totalbl', '0') or '0'))
            except (InvalidOperation, ValueError, TypeError):
                requested_total_bl = Decimal('0')

            details_token = str(getattr(requisition, 'details_permits_number', '') or '').strip()
            permit_tokens = [str(token).strip() for token in details_token.split(',') if str(token).strip()]
            if not permit_tokens:
                try:
                    permit_count = int(getattr(requisition, 'requisiton_number_of_permits', 0) or 0)
                except (TypeError, ValueError):
                    permit_count = 0
                permit_count = max(0, permit_count)
                if permit_count > 0:
                    permit_tokens = [str(i) for i in range(1, permit_count + 1)]
            permit_count = len(permit_tokens)

        if permit_count > 0 and requested_total_bl > 0:
            base = (requested_total_bl / Decimal(str(permit_count))).quantize(Decimal('0.01'), rounding=ROUND_DOWN)
            remainder = (requested_total_bl - (base * Decimal(str(permit_count - 1)))).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            for idx, token in enumerate(permit_tokens):
                expected_by_permit[token] = remainder if idx == permit_count - 1 else base

        permit_numbers_in_rows = []
        for row in tanker_details:
            if isinstance(row, dict):
                token = str(row.get('permit_no') or row.get('permitNo') or row.get('permit') or '').strip()
                permit_numbers_in_rows.append(token)
            else:
                permit_numbers_in_rows.append('')
        any_permit_provided = any(bool(x) for x in permit_numbers_in_rows)

        sum_by_permit = {}
        for idx, row in enumerate(tanker_details, start=1):
            if not isinstance(row, dict):
                raise serializers.ValidationError({
                    'tanker_details': f'Row {idx} must be an object with tanker_no and bulk_liter.'
                })

            permit_no = str(row.get('permit_no') or row.get('permitNo') or row.get('permit') or '').strip()
            if permit_count > 0:
                # Backward compatibility: older submissions had one row per permit and no permit_no.
                if not any_permit_provided and len(tanker_details) == permit_count:
                    permit_no = permit_tokens[idx - 1]
                if not permit_no:
                    raise serializers.ValidationError({
                        'tanker_details': f'Permit number is required for row {idx}.'
                    })
                if permit_no not in expected_by_permit:
                    raise serializers.ValidationError({
                        'tanker_details': f'Invalid permit number "{permit_no}" for row {idx}.'
                    })

            tanker_no = str(row.get('tanker_no', '')).strip()
            if not tanker_no:
                raise serializers.ValidationError({
                    'tanker_details': f'Tanker number is required for row {idx}.'
                })

            try:
                bulk_liter = Decimal(str(row.get('bulk_liter', '0')))
            except (InvalidOperation, ValueError, TypeError):
                raise serializers.ValidationError({
                    'tanker_details': f'Bulk liter must be numeric for row {idx}.'
                })

            if bulk_liter <= 0:
                raise serializers.ValidationError({
                    'tanker_details': f'Bulk liter must be greater than 0 for row {idx}.'
                })

            if permit_count > 0:
                sum_by_permit[permit_no] = (sum_by_permit.get(permit_no, Decimal('0')) + bulk_liter)

            total_bulk_liter += bulk_liter
            normalized_rows.append({
                'permit_no': permit_no if permit_no else None,
                'tanker_no': tanker_no,
                'bulk_liter': str(bulk_liter)
            })

        if permit_count > 0 and requested_total_bl > 0:
            # Partial submissions allowed: validate only the permits present in this payload.
            mismatched = []
            for token, total in sum_by_permit.items():
                expected = expected_by_permit.get(token, Decimal('0'))
                got = total.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                if expected > 0 and got != expected:
                    mismatched.append(f"{token} (expected {expected}, got {got})")
            if mismatched:
                raise serializers.ValidationError({
                    'tanker_details': f"Permit-wise bulk liter mismatch: {', '.join(mismatched)}."
                })

        if requested_total_bl > 0 and total_bulk_liter > requested_total_bl:
            raise serializers.ValidationError({
                'tanker_details': (
                    f"Total bulk liter ({total_bulk_liter}) cannot exceed requisition total quantity "
                    f"({requested_total_bl})."
                )
            })

        attrs['tanker_count'] = tanker_count
        attrs['tanker_details'] = normalized_rows
        attrs['total_bulk_liter'] = total_bulk_liter
        return attrs
