from rest_framework import serializers
from django.db import transaction, models
from decimal import Decimal, InvalidOperation
from django.core.exceptions import ObjectDoesNotExist
from .models import EnaRequisitionDetail, RequisitionBulkLiterDetail
from auth.workflow.constants import WORKFLOW_IDS
from models.masters.license.models import License
import re
from models.transactional.supply_chain.access_control import condition_role_matches

class EnaRequisitionDetailSerializer(serializers.ModelSerializer):
    allowed_actions = serializers.SerializerMethodField()
    allowed_action_configs = serializers.SerializerMethodField()
    can_initiate_cancellation = serializers.SerializerMethodField()
    has_active_revalidation = serializers.SerializerMethodField()
    establishment_name = serializers.SerializerMethodField()
    
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
        try:
            arrival = instance.bulk_liter_detail
            data['has_arrival_details'] = True
            data['arrival_total_bulk_liter'] = str(arrival.total_bulk_liter or '0')
            data['arrival_tanker_count'] = int(arrival.tanker_count or 0)
            data['arrival_approval_status'] = arrival.approval_status or 'PENDING'
            data['arrival_submitted_at'] = arrival.submitted_at.isoformat() if arrival.submitted_at else None
            data['arrival_reviewed_at'] = arrival.reviewed_at.isoformat() if arrival.reviewed_at else None
            data['arrival_reviewed_by'] = arrival.reviewed_by or ''
            data['arrival_review_remarks'] = arrival.review_remarks or ''
        except ObjectDoesNotExist:
            data['has_arrival_details'] = False
            data['arrival_total_bulk_liter'] = '0'
            data['arrival_tanker_count'] = 0
            data['arrival_approval_status'] = ''
            data['arrival_submitted_at'] = None
            data['arrival_reviewed_at'] = None
            data['arrival_reviewed_by'] = ''
            data['arrival_review_remarks'] = ''
        
        # Ensure status_code is set - derive from stage if not set
        if not instance.status_code or instance.status_code == 'RQ_00':
            data['status_code'] = self._derive_status_code_from_stage(instance)
        else:
            data['status_code'] = instance.status_code
        
        print(f"DEBUG: Serializing requisition {instance.id}")
        print(f"  - our_ref_no: '{instance.our_ref_no}' -> '{data['our_ref_no']}'")
        print(f"  - lifted_from: '{instance.lifted_from}' -> '{data['lifted_from']}'")
        print(f"  - via_route: '{instance.via_route}' -> '{data['via_route']}'")
        print(f"  - check_post_name: '{instance.check_post_name}' -> '{data['check_post_name']}'")
        print(f"  - branch_purpose: '{instance.branch_purpose}' -> '{data['branch_purpose']}'")
        print(f"  - lifted_from_distillery_name: '{instance.lifted_from_distillery_name}' -> '{data['lifted_from_distillery_name']}'")
        print(f"  - purpose_name: '{instance.purpose_name}' -> '{data['purpose_name']}'")
        print(f"  - totalbl: {instance.totalbl} -> '{data['totalbl']}'")
        print(f"  - status: '{instance.status}' -> '{data['status']}'")
        print(f"  - status_code: '{instance.status_code}' -> '{data['status_code']}'")
        
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
        
        # Map common stage names to status codes
        stage_lower = stage_name.lower().replace(' ', '').replace('_', '')
        
        stage_code_map = {
            'pending': 'RQ_00',
            'submitted': 'RQ_01',
            'underreview': 'RQ_02',
            'forwardedtopermitsection': 'RQ_03',
            'forwardedpaysliptopermitsection': 'RQ_04',
            'approvedbypermitsection': 'RQ_05',
            'forwardedtocommissioner': 'RQ_06',
            'approvedbycommissioner': 'RQ_09',
            'approved': 'RQ_09',
            'rejected': 'RQ_10',
            'rejectedbycommissioner': 'RQ_10',
        }
        
        return stage_code_map.get(stage_lower, instance.status_code or 'RQ_00')

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
        from auth.workflow.models import WorkflowTransition, WorkflowStage
        
        current_stage = obj.current_stage
        if not current_stage:
            try:
                # Prefer explicit workflow on the object; fallback to ENA Requisition workflow id.
                if obj.workflow_id:
                    current_stage = WorkflowStage.objects.get(workflow_id=obj.workflow_id, name=obj.status)
                else:
                    current_stage = WorkflowStage.objects.get(
                        workflow_id=WORKFLOW_IDS['ENA_REQUISITION'],
                        name=obj.status
                    )
            except WorkflowStage.DoesNotExist:
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
                print(f"Error getting config for action {action_name}: {e}")
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
        
        print(f"DEBUG get_can_initiate_cancellation: obj.id={obj.id}")
        print(f"  - request: {request}")
        print(f"  - request.user: {request.user if request else 'NO REQUEST'}")
        
        if not request or not request.user.is_authenticated:
            print(f"  - FAILED: No request or user not authenticated")
            return False
            
        # Only Licensee can initiate cancellation
        user_role_name = request.user.role.name if hasattr(request.user, 'role') and request.user.role else None
        print(f"  - user_role_name: {user_role_name}")
        
        if user_role_name not in ['licensee', 'Licensee']:
            print(f"  - FAILED: User is not a licensee")
            return False

        status_lower = str(obj.status or '').lower()
        stage_name_lower = str(obj.current_stage.name or '').lower() if obj.current_stage else ''
        status_code = str(getattr(obj, 'status_code', '') or '').upper()

        current_stage_name = obj.current_stage.name if obj.current_stage else 'None'
        is_final_stage = getattr(obj.current_stage, 'is_final', False) if obj.current_stage else False
        approved_markers = ['approvedbycommissioner', 'approved']
        looks_approved = any(marker in status_lower or marker in stage_name_lower for marker in approved_markers)
        is_final_approved = is_final_stage or status_code == 'RQ_09' or looks_approved

        print(f"  - current_stage: {current_stage_name}")
        print(f"  - is_final_stage: {is_final_stage}")
        print(f"  - status_code: {status_code}")
        print(f"  - looks_approved: {looks_approved}")
        print(f"  - is_final_approved: {is_final_approved}")

        if not is_final_approved:
            print(f"  - FAILED: Not in a commissioner-approved final state")
            return False
        
        # Check if it's approved (not rejected)
        
        print(f"  - status: {obj.status}")
        print(f"  - stage_name: {current_stage_name}")
        
        # If status or stage name contains 'reject', it's not approved
        if 'reject' in status_lower or 'reject' in stage_name_lower:
            print(f"  - FAILED: Status or stage contains 'reject'")
            return False
        
        # Check if there's an active revalidation - if yes, cannot cancel
        has_active_reval = self.get_has_active_revalidation(obj)
        print(f"  - has_active_revalidation: {has_active_reval}")
        
        if has_active_reval:
            print(f"  - FAILED: Has active revalidation")
            return False

        # Check if all requisition permits are already cancelled by commissioner-approved cancellations
        if self._are_all_requisition_permits_cancelled(obj):
            print(f"  - FAILED: All permits already cancelled for requisition")
            return False
        
        # Check if already cancelled or cancellation in progress
        if 'cancel' in status_lower or 'cancel' in stage_name_lower:
            print(f"  - FAILED: Already cancelled or in progress")
            return False
        
        print(f"  - SUCCESS: Can initiate cancellation!")
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
            
            # Look for revalidations that:
            # 1. Belong to the same licensee
            # 2. Were created recently (within 90 days)
            # 3. Are not in a final/completed state (status_code not ending in approved/rejected/cancelled)
            active_revalidations = EnaRevalidationDetail.objects.filter(
                licensee_id=obj.licensee_id,
                created_at__gte=ninety_days_ago
            ).exclude(
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
            print(f"Error checking active revalidation: {e}")
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
            print(f"Workflow initialization failed: {e}")
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

        for idx, row in enumerate(tanker_details, start=1):
            if not isinstance(row, dict):
                raise serializers.ValidationError({
                    'tanker_details': f'Row {idx} must be an object with tanker_no and bulk_liter.'
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

            total_bulk_liter += bulk_liter
            normalized_rows.append({
                'tanker_no': tanker_no,
                'bulk_liter': str(bulk_liter)
            })

        requisition = attrs.get('requisition') or getattr(self.instance, 'requisition', None)
        requested_total_bl = Decimal('0')
        if requisition is not None:
            try:
                requested_total_bl = Decimal(str(getattr(requisition, 'totalbl', '0') or '0'))
            except (InvalidOperation, ValueError, TypeError):
                requested_total_bl = Decimal('0')

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
