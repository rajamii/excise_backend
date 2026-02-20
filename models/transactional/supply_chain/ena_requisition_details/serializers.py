from rest_framework import serializers
from django.db import transaction
from .models import EnaRequisitionDetail
from auth.workflow.constants import WORKFLOW_IDS
import re
from models.transactional.supply_chain.access_control import condition_role_matches

class EnaRequisitionDetailSerializer(serializers.ModelSerializer):
    allowed_actions = serializers.SerializerMethodField()
    can_initiate_cancellation = serializers.SerializerMethodField()
    
    current_stage_name = serializers.CharField(source='current_stage.name', read_only=True)
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
        
        return data

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
        if self.get_can_initiate_cancellation(obj):
            if 'REQUEST_CANCELLATION' not in actions:
                actions.append('REQUEST_CANCELLATION')

        if not actions:
            return []
        
        from auth.workflow.services import WorkflowService
        configs = []
        for action_name in actions:
            config = WorkflowService.get_action_config(action_name)
            configs.append(config)
        
        return configs

    def get_can_initiate_cancellation(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return False
            
        # Only Licensee can initiate cancellation
        user_role_name = request.user.role.name if hasattr(request.user, 'role') and request.user.role else None
        if user_role_name not in ['licensee', 'Licensee']:
            return False

        # Status must be 'RQ_09' (Approved)
        # We explicitly check for the code here in the backend business logic
        return obj.status_code == 'RQ_09'

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
