from rest_framework import viewsets, status, permissions, serializers
from rest_framework.decorators import action
from rest_framework.response import Response
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.shortcuts import get_object_or_404
from django.db import transaction as db_transaction, models
from decimal import Decimal
import logging
import re
from .models import HologramProcurement, HologramRequest, HologramRollsDetails
from .serializers import HologramProcurementSerializer, HologramRequestSerializer
from auth.workflow.models import Workflow, WorkflowStage, WorkflowTransition, Transaction, StagePermission
from auth.workflow.constants import WORKFLOW_IDS
from models.masters.supply_chain.profile.models import SupplyChainUserProfile, UserManufacturingUnit
from models.transactional.supply_chain.access_control import scope_by_profile_or_workflow

HOLOGRAM_REF_PREFIX = 'HQR'
HOLOGRAM_REF_DISTRICT_CODE = '1101'

logger = logging.getLogger(__name__)

def _normalize_role_name(role_name):
    return ''.join(ch for ch in str(role_name or '').lower() if ch.isalnum())

def _canonical_role_token(role_name):
    token = _normalize_role_name(role_name)
    if token in {'offcierincharge', 'officerincharge', 'officercharge', 'oic'}:
        return 'officerincharge'
    if token in {'permitsection', 'permit_section', 'permit-section'}:
        return 'permitsection'
    if token in {'itcell', 'it_cell', 'it-cell'}:
        return 'itcell'
    if token in {'jointcommissioner', 'commissioner'}:
        return 'commissioner'
    return token


def _is_scoped_officer_or_licensee(role_name_token):
    return role_name_token in {'licensee', 'officerincharge', 'offcierincharge', 'oic'}

def _get_user_role_id(user):
    return getattr(user, 'role_id', None) if user and user.is_authenticated else None

def _condition_role_matches(cond, user):
    role_id = _get_user_role_id(user)
    cond_role_id = cond.get('role_id')

    # DB-driven primary match by role_id
    if cond_role_id is not None:
        if role_id is None:
            return False
        try:
            return int(cond_role_id) == int(role_id)
        except (TypeError, ValueError):
            return False

    # Backward compatibility fallback using role name in condition
    cond_role = _canonical_role_token(cond.get('role'))
    if cond_role:
        user_role_name = _canonical_role_token(getattr(getattr(user, 'role', None), 'name', ''))
        return cond_role == user_role_name

    # No role restriction in condition
    return True

def _collect_role_stage_ids(workflow_id, user):
    transitions = WorkflowTransition.objects.filter(workflow_id=workflow_id).select_related('from_stage', 'to_stage')

    # Seed stages where this role can take an action
    seeds = set()
    edges = {}
    for t in transitions:
        edges.setdefault(t.from_stage_id, set()).add(t.to_stage_id)

        cond = t.condition or {}
        if _condition_role_matches(cond, user):
            seeds.add(t.from_stage_id)
            seeds.add(t.to_stage_id)

    # Include all downstream stages so users retain historical visibility naturally
    visible = set(seeds)
    stack = list(seeds)
    while stack:
        current = stack.pop()
        for nxt in edges.get(current, set()):
            if nxt not in visible:
                visible.add(nxt)
                stack.append(nxt)

    return visible

def _get_visible_stage_ids_for_user(user, workflow_id):
    visible = set()

    # DB stage permission grants immediate visibility to configured stages
    if hasattr(user, 'role') and user.role:
        perm_stage_ids = StagePermission.objects.filter(
            role=user.role,
            can_process=True,
            stage__workflow_id=workflow_id
        ).values_list('stage_id', flat=True)
        visible.update(perm_stage_ids)

    # Transition-role graph grants workflow-driven visibility including downstream history
    visible.update(_collect_role_stage_ids(workflow_id, user))
    return visible

def _apply_transition_by_action(instance, acting_user, action_name, remarks=''):
    """
    Move an instance through workflow transition graph using action from DB conditions.
    Avoids hardcoded stage-name checks.
    """
    if not instance or not instance.workflow or not instance.current_stage:
        return None

    normalized_action = str(action_name or '').strip().lower()
    if not normalized_action:
        return None

    transitions = WorkflowTransition.objects.filter(
        workflow=instance.workflow,
        from_stage=instance.current_stage
    ).order_by('id')

    selected = None
    for transition in transitions:
        cond = transition.condition or {}
        cond_action = str(cond.get('action') or '').strip().lower()
        if cond_action != normalized_action:
            continue
        if _condition_role_matches(cond, acting_user):
            selected = transition
            break
        if selected is None:
            # Backward compatible fallback when role info is missing/inconsistent.
            selected = transition

    if not selected:
        return None

    instance.current_stage = selected.to_stage
    instance.save(update_fields=['current_stage'])

    Transaction.objects.create(
        application=instance,
        stage=selected.to_stage,
        performed_by=acting_user,
        remarks=remarks or f"Action '{normalized_action}' performed"
    )

    return selected.to_stage

def _get_or_create_active_supply_chain_profile(user):
    profile = SupplyChainUserProfile.objects.filter(user=user).first()
    active_license, establishment_name, site_address, license_type = _resolve_license_context(user)
    if profile:
        update_fields = []
        if establishment_name and profile.manufacturing_unit_name != establishment_name:
            profile.manufacturing_unit_name = establishment_name
            update_fields.append('manufacturing_unit_name')
        if active_license and profile.licensee_id != active_license.license_id:
            profile.licensee_id = active_license.license_id
            update_fields.append('licensee_id')
        if site_address and profile.address != site_address:
            profile.address = site_address
            update_fields.append('address')
        if license_type and profile.license_type != license_type:
            profile.license_type = license_type
            update_fields.append('license_type')
        if update_fields:
            profile.save(update_fields=update_fields)
        return profile

    latest_unit = UserManufacturingUnit.objects.filter(user=user).order_by('-updated_at', '-id').first()
    if latest_unit:
        profile, _ = SupplyChainUserProfile.objects.update_or_create(
            user=user,
            defaults={
                'manufacturing_unit_name': latest_unit.manufacturing_unit_name,
                'licensee_id': latest_unit.licensee_id,
                'license_type': latest_unit.license_type,
                'address': latest_unit.address,
            }
        )
        return profile

    if not (active_license and establishment_name):
        return None

    profile, _ = SupplyChainUserProfile.objects.update_or_create(
        user=user,
        defaults={
            'manufacturing_unit_name': establishment_name,
            'licensee_id': active_license.license_id,
            'license_type': license_type,
            'address': site_address,
        }
    )
    UserManufacturingUnit.objects.update_or_create(
        user=user,
        licensee_id=active_license.license_id,
        defaults={
            'manufacturing_unit_name': establishment_name,
            'license_type': license_type,
            'address': site_address,
        }
    )
    return profile


def _resolve_roll_license_id(procurement, acting_user=None):
    """
    Resolve license_id to persist on hologram_rolls_details.
    Priority keeps OIC-mapped ownership explicit at submit/arrival time.
    """
    candidates = []

    if acting_user is not None:
        assignment = getattr(acting_user, 'oic_assignment', None)
        if assignment is not None:
            candidates.extend([
                getattr(assignment, 'licensee_id', ''),
                getattr(getattr(assignment, 'license', None), 'license_id', ''),
            ])
        candidates.append(getattr(getattr(acting_user, 'supply_chain_profile', None), 'licensee_id', ''))

    candidates.extend([
        getattr(getattr(procurement, 'license', None), 'license_id', ''),
        getattr(getattr(procurement, 'licensee', None), 'licensee_id', ''),
    ])

    for value in candidates:
        normalized = str(value or '').strip()
        if normalized:
            return normalized

    return ''


def _resolve_request_license_id(profile=None, acting_user=None):
    """
    Resolve license_id to persist on hologram_request.
    """
    candidates = []

    if acting_user is not None:
        assignment = getattr(acting_user, 'oic_assignment', None)
        if assignment is not None:
            candidates.extend([
                getattr(assignment, 'licensee_id', ''),
                getattr(getattr(assignment, 'license', None), 'license_id', ''),
            ])
        candidates.append(getattr(getattr(acting_user, 'supply_chain_profile', None), 'licensee_id', ''))

    if profile is not None:
        candidates.append(getattr(profile, 'licensee_id', ''))

    for value in candidates:
        normalized = str(value or '').strip()
        if normalized:
            return normalized

    return ''


def _resolve_license_context(user):
    active_license = None
    establishment_name = ''
    site_address = ''
    license_type = 'Distillery'

    try:
        from models.masters.license.models import License
        from models.transactional.new_license_application.models import NewLicenseApplication

        active_license = (
            License.objects.filter(
                applicant=user,
                source_type='new_license_application',
                is_active=True
            )
            .order_by('-issue_date', '-license_id')
            .first()
        )

        if not active_license:
            active_license = (
                License.objects.filter(
                    applicant=user,
                    is_active=True
                )
                .order_by('-issue_date', '-license_id')
                .first()
            )

        if active_license:
            source = getattr(active_license, 'source_application', None)
            establishment_name = str(getattr(source, 'establishment_name', '') or '').strip()
            site_address = str(getattr(source, 'site_address', '') or '').strip()

            if not establishment_name and active_license.source_object_id:
                app = NewLicenseApplication.objects.filter(
                    application_id=str(active_license.source_object_id).strip()
                ).only('establishment_name', 'site_address').first()
                if app:
                    establishment_name = str(getattr(app, 'establishment_name', '') or '').strip()
                    site_address = str(getattr(app, 'site_address', '') or '').strip()

            category_name = str(getattr(getattr(active_license, 'license_category', None), 'category_name', '') or '').lower()
            if 'beer' in category_name or 'brewery' in category_name:
                license_type = 'Brewery'
    except Exception:
        return None, '', '', 'Distillery'

    return active_license, establishment_name, site_address, license_type

def _generate_financial_year(now_dt=None):
    dt = timezone.localtime(now_dt) if now_dt else timezone.localtime()
    year = dt.year
    if dt.month >= 4:
        return f"{year}-{str(year + 1)[2:]}"
    return f"{year - 1}-{str(year)[2:]}"

def _generate_hologram_ref_no(model_cls):
    financial_year = _generate_financial_year()
    prefix = f"{HOLOGRAM_REF_PREFIX}/{HOLOGRAM_REF_DISTRICT_CODE}/{financial_year}"

    last_obj = model_cls.objects.filter(
        ref_no__startswith=prefix
    ).select_for_update().order_by('-ref_no').first()

    last_number = 0
    if last_obj and getattr(last_obj, 'ref_no', None):
        try:
            last_number = int(str(last_obj.ref_no).split('/')[-1])
        except (TypeError, ValueError):
            last_number = 0

    return f"{prefix}/{str(last_number + 1).zfill(4)}"

class HologramProcurementViewSet(viewsets.ModelViewSet):
    queryset = HologramProcurement.objects.all()
    serializer_class = HologramProcurementSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        
        # Prefetch transactions for edit history
        queryset = super().get_queryset().prefetch_related('transactions', 'transactions__performed_by')
        
        if not user.is_authenticated:
            return queryset.none()
            
        user_role_name = _normalize_role_name(getattr(getattr(user, 'role', None), 'name', ''))

        if _is_scoped_officer_or_licensee(user_role_name):
            return scope_by_profile_or_workflow(
                user=user,
                queryset=queryset,
                workflow_id=WORKFLOW_IDS['HOLOGRAM_PROCUREMENT'],
                licensee_field='licensee__licensee_id'
            )

        visible_stage_ids = _get_visible_stage_ids_for_user(
            user=user,
            workflow_id=WORKFLOW_IDS['HOLOGRAM_PROCUREMENT']
        )
        if visible_stage_ids:
            return queryset.filter(current_stage_id__in=visible_stage_ids).order_by('-date')
            
        # Fallback: return all for authenticated users (Commissioner can see all)
        return queryset.order_by('-date')

    def perform_create(self, serializer):
        profile = _get_or_create_active_supply_chain_profile(self.request.user)
        license, manufacturing_unit_name, _, _ = _resolve_license_context(self.request.user)
        
        # If no license found or no establishment name, try profile
        if not manufacturing_unit_name and profile:
            manufacturing_unit_name = profile.manufacturing_unit_name

        if not license and profile and profile.licensee_id:
            try:
                from models.masters.license.models import License
                license = License.objects.filter(
                    license_id=profile.licensee_id,
                    is_active=True
                ).first()
            except Exception:
                license = None

        if not profile and license and manufacturing_unit_name:
            profile = _get_or_create_active_supply_chain_profile(self.request.user)
        
        # If still no manufacturing unit name, raise error
        if not manufacturing_unit_name:
            raise serializers.ValidationError({
                'detail': 'No manufacturing unit found. Please ensure you have an active license.'
            })
        if not profile:
            raise serializers.ValidationError({
                'detail': 'No active supply chain profile found. Select your manufacturing unit first.'
            })
        
        with db_transaction.atomic():
            ref_no = _generate_hologram_ref_no(HologramProcurement)

            # Get initial workflow stage
            try:
                workflow = Workflow.objects.get(id=WORKFLOW_IDS['HOLOGRAM_PROCUREMENT'])
                initial_stage = WorkflowStage.objects.get(workflow=workflow, is_initial=True)
            except Workflow.DoesNotExist:
                # Fallback or error - Should be populated via command
                raise serializers.ValidationError("Workflow configuration missing.")

            instance = serializer.save(
                ref_no=ref_no,
                licensee=profile,
                license=license,
                workflow=workflow,
                current_stage=initial_stage,
                manufacturing_unit=manufacturing_unit_name
            )
            
            # Log initial transaction
            Transaction.objects.create(
                application=instance,
                stage=initial_stage,
                performed_by=self.request.user,
                remarks='Hologram Procurement Application Submitted'
            )

    @action(detail=True, methods=['post'])
    def perform_action(self, request, pk=None):
        instance = self.get_object()
        action_name = request.data.get('action')
        remarks = request.data.get('remarks', '')
        
        if not action_name:
            return Response({'error': 'Action is required'}, status=status.HTTP_400_BAD_REQUEST)

        normalized_action = str(action_name or '').strip().lower()
        wallet_result = None

        # Find transition matching current stage and action
        transitions = WorkflowTransition.objects.filter(
            workflow=instance.workflow,
            from_stage=instance.current_stage
        )
        
        selected_transition = None
        for t in transitions:
            cond = t.condition or {}
            cond_action = str(cond.get('action') or '').lower()
            role_ok = _condition_role_matches(cond, request.user)
            action_ok = cond_action == str(action_name).lower()
            if role_ok and action_ok:
                selected_transition = t
                break
                
        if selected_transition:
            with db_transaction.atomic():
                if normalized_action == 'pay':
                    wallet_result = self._debit_hologram_wallet_for_payment(instance, request.user)

                instance.current_stage = selected_transition.to_stage
                
                # CRITICAL: Save carton_details if provided with the action
                if normalized_action == 'assign_cartons':
                    carton_details = request.data.get('carton_details')
                    if carton_details:
                        arrival_processed_date = request.data.get('arrival_processed_date')
                        arrival_ts = parse_datetime(str(arrival_processed_date)) if arrival_processed_date else None
                        if arrival_ts and timezone.is_naive(arrival_ts):
                            arrival_ts = timezone.make_aware(arrival_ts)
                        if not arrival_ts:
                            arrival_ts = timezone.now()

                        # Ensure each carton carries an arrival timestamp for roll-level display.
                        for detail in carton_details:
                            if isinstance(detail, dict):
                                has_arrived_value = (
                                    detail.get('arrivedDate') or
                                    detail.get('arrived_date') or
                                    detail.get('arrival_date')
                                )
                                if not has_arrived_value:
                                    detail['arrivedDate'] = arrival_ts.isoformat()

                        self._validate_assign_cartons(instance, carton_details)
                        instance.carton_details = carton_details
                        instance.arrival_date = arrival_ts
                        # Sync to new table
                        self._sync_rolls_details(instance, carton_details, acting_user=request.user, mark_received_by=False)

                instance.save()
                
                # Check for Arrival Confirmation to ensure sync
                if normalized_action in ['confirm_arrival', 'arrival_confirmed', 'confirm arrival', 'confirm']:
                    if not instance.arrival_date:
                        instance.arrival_date = timezone.now()
                    if instance.carton_details:
                        self._sync_rolls_details(instance, instance.carton_details, acting_user=request.user, mark_received_by=True)
                    # Backfill received-by for any existing rolls under this procurement.
                    try:
                        display = _get_user_display_name(request.user)
                        HologramRollsDetails.objects.filter(
                            procurement=instance
                        ).filter(
                            models.Q(received_by_id__isnull=True) |
                            models.Q(received_by_display_name__isnull=True) |
                            models.Q(received_by_display_name='')
                        ).update(
                            received_by=request.user,
                            received_by_display_name=display,
                            confirmed_at=timezone.now(),
                            updated_by=request.user,
                        )
                    except Exception:
                        logger.exception(
                            "Failed to backfill received-by for procurement=%s",
                            getattr(instance, "id", None),
                        )

                if normalized_action == 'pay':
                    instance.payment_status = 'completed'
                    payment_details = dict(instance.payment_details or {})
                    history = list(payment_details.get('wallet_history') or [])
                    history.append({
                        'transaction_id': wallet_result.get('transaction_id') if wallet_result else '',
                        'amount': str(wallet_result.get('amount')) if wallet_result else '0',
                        'wallet_type': wallet_result.get('wallet_type') if wallet_result else 'hologram',
                        'head_of_account': wallet_result.get('head_of_account') if wallet_result else '',
                        'paid_at': timezone.now().isoformat(),
                        'paid_by': str(getattr(request.user, 'username', '') or ''),
                        'reference_no': instance.ref_no
                    })
                    payment_details.update({
                        'wallet_payment': float(wallet_result.get('amount')) if wallet_result else float(payment_details.get('wallet_payment') or 0),
                        'total_amount': float(wallet_result.get('amount')) if wallet_result else float(payment_details.get('total_amount') or 0),
                        'payment_mode': 'wallet',
                        'payment_status': 'completed',
                        'paid_at': timezone.now().isoformat(),
                        'wallet_history': history
                    })
                    instance.payment_details = payment_details
                    instance.save(update_fields=['payment_status', 'payment_details'])

                Transaction.objects.create(
                    application=instance,
                    stage=selected_transition.to_stage,
                    performed_by=self.request.user,
                    remarks=remarks or f"Action '{action_name}' performed"
                )
        else:
            # ALLOW UPDATE: If action is 'assign_cartons' and we have details, allow update without transition
            # This handles re-submission of carton details for records already in 'Cartoon Assigned' or 'Arrived' state
            
            if normalized_action == 'assign_cartons':
                carton_details = request.data.get('carton_details')
                if carton_details:
                    arrival_processed_date = request.data.get('arrival_processed_date')
                    arrival_ts = parse_datetime(str(arrival_processed_date)) if arrival_processed_date else None
                    if arrival_ts and timezone.is_naive(arrival_ts):
                        arrival_ts = timezone.make_aware(arrival_ts)
                    if not arrival_ts:
                        arrival_ts = timezone.now()

                    for detail in carton_details:
                        if isinstance(detail, dict):
                            has_arrived_value = (
                                detail.get('arrivedDate') or
                                detail.get('arrived_date') or
                                detail.get('arrival_date')
                            )
                            if not has_arrived_value:
                                detail['arrivedDate'] = arrival_ts.isoformat()

                    self._validate_assign_cartons(instance, carton_details)
                    instance.carton_details = carton_details
                    instance.arrival_date = arrival_ts
                    self._sync_rolls_details(instance, carton_details, acting_user=request.user, mark_received_by=False)
            elif normalized_action in ['confirm_arrival', 'arrival_confirmed', 'confirm arrival', 'confirm']:
                if not instance.arrival_date:
                    instance.arrival_date = timezone.now()
                if instance.carton_details:
                    self._sync_rolls_details(instance, instance.carton_details, acting_user=request.user, mark_received_by=True)
                try:
                    display = _get_user_display_name(request.user)
                    HologramRollsDetails.objects.filter(
                        procurement=instance
                    ).filter(
                        models.Q(received_by_id__isnull=True) |
                        models.Q(received_by_display_name__isnull=True) |
                        models.Q(received_by_display_name='')
                    ).update(
                        received_by=request.user,
                        received_by_display_name=display,
                        confirmed_at=timezone.now(),
                        updated_by=request.user,
                    )
                except Exception:
                    logger.exception(
                        "Failed to backfill received-by for procurement=%s (no-transition confirm)",
                        getattr(instance, "id", None),
                    )

            if normalized_action == 'pay':
                wallet_result = self._debit_hologram_wallet_for_payment(instance, request.user)
                instance.payment_status = 'completed'
                payment_details = dict(instance.payment_details or {})
                history = list(payment_details.get('wallet_history') or [])
                history.append({
                    'transaction_id': wallet_result.get('transaction_id') if wallet_result else '',
                    'amount': str(wallet_result.get('amount')) if wallet_result else '0',
                    'wallet_type': wallet_result.get('wallet_type') if wallet_result else 'hologram',
                    'head_of_account': wallet_result.get('head_of_account') if wallet_result else '',
                    'paid_at': timezone.now().isoformat(),
                    'paid_by': str(getattr(request.user, 'username', '') or ''),
                    'reference_no': instance.ref_no
                })
                payment_details.update({
                    'wallet_payment': float(wallet_result.get('amount')) if wallet_result else float(payment_details.get('wallet_payment') or 0),
                    'total_amount': float(wallet_result.get('amount')) if wallet_result else float(payment_details.get('total_amount') or 0),
                    'payment_mode': 'wallet',
                    'payment_status': 'completed',
                    'paid_at': timezone.now().isoformat(),
                    'wallet_history': history
                })
                instance.payment_details = payment_details
                instance.save(update_fields=['payment_status', 'payment_details'])
            
            instance.save()
            
            Transaction.objects.create(
                application=instance,
                stage=instance.current_stage,
                performed_by=self.request.user,
                remarks=remarks or f"Action '{action_name}' performed"
            )

        instance.save()
        response_payload = self.get_serializer(instance).data
        if wallet_result is not None:
            response_payload['wallet_deduction'] = wallet_result
        return Response(response_payload)

    def _normalize_carton_key(self, value):
        text = str(value or '').strip().lower()
        if not text:
            return ''
        text = text.split('/')[-1].strip()
        text = re.sub(r'\([a-z]+\)$', '', text).strip()
        return re.sub(r'\s+', '', text)

    def _normalize_exact_carton_key(self, value):
        text = str(value or '').strip().lower()
        if not text:
            return ''
        text = text.split('/')[-1].strip()
        return re.sub(r'\s+', '', text)

    def _normalize_serial_key(self, value):
        text = str(value or '').strip()
        if not text:
            return ''
        match = re.search(r'\d+', text)
        if match:
            return str(int(match.group(0)))
        return text.lower()

    def _validate_assign_cartons(self, instance, carton_details):
        if not isinstance(carton_details, list):
            raise serializers.ValidationError({'detail': 'Invalid carton details payload.'})

        instance_license_id = str(
            getattr(getattr(instance, 'license', None), 'license_id', '') or
            getattr(getattr(instance, 'licensee', None), 'licensee_id', '') or
            ''
        ).strip()

        incoming_exact_carton_keys = set()
        incoming_base_carton_keys = set()
        incoming_range_keys = set()

        for item in carton_details:
            exact_carton_key = self._normalize_exact_carton_key(
                item.get('cartoonNumber') or
                item.get('cartoon_number') or
                item.get('carton_number') or
                item.get('baseCartoonNumber')
            )
            base_carton_key = self._normalize_carton_key(
                item.get('cartoonNumber') or
                item.get('cartoon_number') or
                item.get('carton_number') or
                item.get('baseCartoonNumber')
            )
            from_key = self._normalize_serial_key(item.get('fromSerial') or item.get('from_serial'))
            to_key = self._normalize_serial_key(item.get('toSerial') or item.get('to_serial'))

            if exact_carton_key:
                if exact_carton_key in incoming_exact_carton_keys:
                    raise serializers.ValidationError({
                        'detail': 'Carton number already exists. Please use another carton number.'
                    })
                incoming_exact_carton_keys.add(exact_carton_key)

            if base_carton_key:
                incoming_base_carton_keys.add(base_carton_key)

            if from_key and to_key:
                range_key = f'{from_key}-{to_key}'
                if range_key in incoming_range_keys:
                    raise serializers.ValidationError({
                        'detail': 'This serial range is already entered before. Please use another range.'
                    })
                incoming_range_keys.add(range_key)

        existing_rolls = HologramRollsDetails.objects.exclude(procurement=instance)

        if instance_license_id:
            existing_rolls = existing_rolls.filter(license_id=instance_license_id)
        else:
            existing_rolls = existing_rolls.filter(
                procurement__licensee=instance.licensee,
                procurement__manufacturing_unit=instance.manufacturing_unit
            )

        existing_rolls = existing_rolls.values(
            'carton_number', 'from_serial', 'to_serial'
        )

        existing_carton_keys = set()
        existing_range_keys = set()
        for row in existing_rolls:
            carton_key = self._normalize_carton_key(row.get('carton_number'))
            from_key = self._normalize_serial_key(row.get('from_serial'))
            to_key = self._normalize_serial_key(row.get('to_serial'))
            if carton_key:
                existing_carton_keys.add(carton_key)
            if from_key and to_key:
                existing_range_keys.add(f'{from_key}-{to_key}')

        if any(key in existing_carton_keys for key in incoming_base_carton_keys):
            raise serializers.ValidationError({
                'detail': 'Carton number already exists for this distillery/brewery. Try another carton number.'
            })

        if any(key in existing_range_keys for key in incoming_range_keys):
            raise serializers.ValidationError({
                'detail': 'This serial range is already entered before. Please use another range.'
            })

    def _debit_hologram_wallet_for_payment(self, instance, user):
        """
        Debit hologram wallet immediately when licensee pays for hologram procurement.
        Persists wallet history in wallet_transactions table.
        """
        from models.transactional.payment.models import WalletBalance, WalletTransaction

        licensee_id = (
            str(getattr(getattr(instance, 'license', None), 'license_id', '') or '').strip() or
            str(getattr(getattr(instance, 'licensee', None), 'licensee_id', '') or '').strip()
        )
        if not licensee_id:
            raise serializers.ValidationError({'error': 'Unable to resolve licensee id for wallet deduction.'})

        total_qty = (
            Decimal(str(instance.local_qty or 0)) +
            Decimal(str(instance.export_qty or 0)) +
            Decimal(str(instance.defence_qty or 0))
        )
        amount = (total_qty * Decimal('0.15')).quantize(Decimal('0.01'))
        if amount <= 0:
            raise serializers.ValidationError({'error': 'Invalid hologram payment amount.'})

        transaction_id = f"HGP-{instance.id}-PAYMENT"
        existing = WalletTransaction.objects.filter(
            transaction_id=transaction_id,
            source_module='hologram_procurement',
            entry_type='DR'
        ).first()
        if existing:
            return {
                'transaction_id': existing.transaction_id,
                'amount': Decimal(str(existing.amount or 0)),
                'wallet_type': existing.wallet_type,
                'head_of_account': existing.head_of_account,
                'balance_after': Decimal(str(existing.balance_after or 0)),
                'reference_no': existing.reference_no,
                'already_processed': True
            }

        with db_transaction.atomic():
            wallet = (
                WalletBalance.objects.select_for_update()
                .filter(licensee_id=licensee_id, wallet_type__iexact='hologram')
                .order_by('wallet_balance_id')
                .first()
            )
            if not wallet:
                raise serializers.ValidationError({
                    'error': f'Hologram wallet not found for licensee_id={licensee_id}.'
                })

            before = Decimal(str(wallet.current_balance or 0))
            if before < amount:
                raise serializers.ValidationError({
                    'error': f'Insufficient hologram wallet balance. Available: {before}, Required: {amount}.'
                })

            after = before - amount
            now_ts = timezone.now()
            wallet.current_balance = after
            wallet.total_debit = Decimal(str(wallet.total_debit or 0)) + amount
            wallet.last_updated_at = now_ts
            wallet.save(update_fields=['current_balance', 'total_debit', 'last_updated_at'])

            WalletTransaction.objects.create(
                wallet_balance=wallet,
                transaction_id=transaction_id,
                licensee_id=licensee_id,
                licensee_name=wallet.licensee_name,
                user_id=str(getattr(user, 'username', '') or wallet.user_id or ''),
                module_type=wallet.module_type,
                wallet_type=wallet.wallet_type,
                head_of_account=wallet.head_of_account,
                entry_type='DR',
                transaction_type='debit',
                amount=amount,
                balance_before=before,
                balance_after=after,
                reference_no=instance.ref_no,
                source_module='hologram_procurement',
                payment_status='success',
                remarks=f'Hologram wallet debit for procurement {instance.ref_no}',
                created_at=now_ts,
            )

        return {
            'transaction_id': transaction_id,
            'amount': amount,
            'wallet_type': wallet.wallet_type,
            'head_of_account': wallet.head_of_account,
            'balance_after': after,
            'reference_no': instance.ref_no,
            'already_processed': False
        }
    
    @action(detail=True, methods=['patch'], url_path='update-quantities')
    def update_quantities(self, request, pk=None):
        """
        Commissioner can edit hologram quantities before approval.
        Updates quantities and recalculates payment amount.
        """
        instance = self.get_object()
        
        # Extract new quantities from request
        local_qty = request.data.get('local_qty')
        export_qty = request.data.get('export_qty')
        defence_qty = request.data.get('defence_qty')
        
        # Validate that at least one quantity is provided
        if local_qty is None and export_qty is None and defence_qty is None:
            return Response(
                {'error': 'At least one quantity field must be provided'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Store original quantities for audit trail
        original_quantities = {
            'local': float(instance.local_qty),
            'export': float(instance.export_qty),
            'defence': float(instance.defence_qty),
            'total': float(instance.local_qty) + float(instance.export_qty) + float(instance.defence_qty)
        }
        
        # Update quantities
        if local_qty is not None:
            instance.local_qty = local_qty
        if export_qty is not None:
            instance.export_qty = export_qty
        if defence_qty is not None:
            instance.defence_qty = defence_qty
        
        # Calculate new totals
        new_total = float(instance.local_qty) + float(instance.export_qty) + float(instance.defence_qty)
        
        # Update payment details with new amount (₹0.15 per hologram)
        new_payment_amount = new_total * 0.15
        if not instance.payment_details:
            instance.payment_details = {}
        instance.payment_details['wallet_payment'] = new_payment_amount
        instance.payment_details['total_amount'] = new_payment_amount
        instance.payment_details['edit_history'] = {
            'editedBy': getattr(self.request.user, 'username', None) or 'Commissioner',
            'editedDate': timezone.now().strftime('%Y-%m-%d'),
            'originalQuantities': {
                'local': original_quantities['local'],
                'export': original_quantities['export'],
                'defence': original_quantities['defence'],
                'total': original_quantities['total'],
            },
            'updatedQuantities': {
                'local': float(instance.local_qty),
                'export': float(instance.export_qty),
                'defence': float(instance.defence_qty),
                'total': new_total,
            },
            'originalPayment': original_quantities['total'] * 0.15,
            'updatedPayment': new_payment_amount,
        }
        
        # Save changes
        instance.save()
        
        # Create transaction log for audit trail
        edit_remarks = (
            "Quantities updated by Commissioner: "
            f"Local {original_quantities['local']} -> {instance.local_qty}, "
            f"Export {original_quantities['export']} -> {instance.export_qty}, "
            f"Defence {original_quantities['defence']} -> {instance.defence_qty}. "
            f"New payment amount: Rs {new_payment_amount:.2f}"
        )
        
        Transaction.objects.create(
            application=instance,
            stage=instance.current_stage,
            performed_by=self.request.user,
            remarks=edit_remarks
        )
        
        # Return updated data
        return Response({
            'success': True,
            'message': 'Quantities updated successfully',
            'data': self.get_serializer(instance).data,
            'original_quantities': original_quantities,
            'updated_quantities': {
                'local': float(instance.local_qty),
                'export': float(instance.export_qty),
                'defence': float(instance.defence_qty),
                'total': new_total
            },
            'new_payment_amount': new_payment_amount
        })

    def _sync_rolls_details(self, procurement, carton_details, acting_user=None, mark_received_by: bool = False):
        """
        Syncs JSON carton details to HologramRollsDetails table
        """
        try:
            
            # Collect all procurement types for fallback logic
            proc_types = []
            if procurement.local_qty and procurement.local_qty > 0:
                proc_types.append('LOCAL')
            if procurement.export_qty and procurement.export_qty > 0:
                proc_types.append('EXPORT')
            if procurement.defence_qty and procurement.defence_qty > 0:
                proc_types.append('DEFENCE')
            
            # Default fallback type (for backward compatibility)
            default_proc_type = proc_types[0] if proc_types else 'LOCAL'
                
            resolved_license_id = _resolve_roll_license_id(procurement, acting_user=acting_user)

            for item in carton_details:
                carton_num = item.get('cartoonNumber') or item.get('cartoon_number') or item.get('carton_number')
                if not carton_num:
                    continue

                received_ts = None
                arrived_value = (
                    item.get('arrivedDate') or
                    item.get('arrived_date') or
                    item.get('arrival_date') or
                    item.get('received_date') or
                    item.get('receivedDate')
                )
                if arrived_value:
                    try:
                        received_ts = parse_datetime(str(arrived_value))
                        if received_ts and timezone.is_naive(received_ts):
                            received_ts = timezone.make_aware(received_ts)
                    except Exception:
                        received_ts = None
                
                defaults = {
                     'type': item.get('type') or default_proc_type,
                     'from_serial': item.get('fromSerial') or item.get('from_serial'),
                     'to_serial': item.get('toSerial') or item.get('to_serial'),
                     'total_count': item.get('numberOfHolograms') or item.get('number_of_holograms') or item.get('total_count', 0),
                }
                if received_ts:
                    defaults['received_date'] = received_ts
                if acting_user:
                    defaults['created_by'] = acting_user
                    defaults['updated_by'] = acting_user
                
                try:
                    defaults['total_count'] = int(defaults['total_count'])
                except:
                    defaults['total_count'] = 0

                # Calculate from serials if count is missing (Fix for 0 issue)
                if defaults['total_count'] == 0 and defaults['from_serial'] and defaults['to_serial']:
                    try:
                        f = int(str(defaults['from_serial']))
                        t = int(str(defaults['to_serial']))
                        defaults['total_count'] = (t - f) + 1
                    except (ValueError, TypeError):
                        pass
                
                # Check for existence
                obj, created = HologramRollsDetails.objects.get_or_create(
                    procurement=procurement,
                    carton_number=carton_num,
                    defaults={
                        **defaults,
                        'license_id': resolved_license_id or None,
                        'available': defaults['total_count'],
                        'status': 'AVAILABLE'
                    }
                )
                
                if created:
                    # CRITICAL: Initialize HologramSerialRange for new roll
                    # Create initial AVAILABLE range covering the entire roll
                    from models.transactional.supply_chain.hologram.models import HologramSerialRange
                    
                    HologramSerialRange.objects.create(
                        roll=obj,
                        from_serial=defaults['from_serial'],
                        to_serial=defaults['to_serial'],
                        count=defaults['total_count'],
                        status='AVAILABLE',
                        description=f'Initial range for roll {carton_num}'
                    )
                    
                    # Update available_range field
                    obj.update_available_range()
                
                if not created:
                    # Update definition fields
                    obj.type = defaults['type']
                    obj.from_serial = defaults['from_serial']
                    obj.to_serial = defaults['to_serial']
                    obj.total_count = defaults['total_count']
                    if resolved_license_id:
                        obj.license_id = resolved_license_id
                    if received_ts and not obj.received_date:
                        obj.received_date = received_ts
                    if acting_user:
                        obj.updated_by = acting_user

                    if mark_received_by and acting_user:
                        if not getattr(obj, 'received_by_id', None):
                            obj.received_by = acting_user
                        if not str(getattr(obj, 'received_by_display_name', '') or '').strip():
                            obj.received_by_display_name = _get_user_display_name(obj.received_by)
                        if not getattr(obj, 'confirmed_at', None):
                            obj.confirmed_at = timezone.now()
                    
                    # Reset available if unused (assuming edit mode)
                    if obj.used == 0 and obj.damaged == 0:
                        obj.available = obj.total_count
                        obj.status = 'AVAILABLE'
                    
                    obj.save()
                else:
                    if mark_received_by and acting_user:
                        changed = False
                        if not getattr(obj, 'received_by_id', None):
                            obj.received_by = acting_user
                            changed = True
                        if not str(getattr(obj, 'received_by_display_name', '') or '').strip():
                            obj.received_by_display_name = _get_user_display_name(obj.received_by)
                            changed = True
                        if not getattr(obj, 'confirmed_at', None):
                            obj.confirmed_at = timezone.now()
                            changed = True
                        if acting_user and not getattr(obj, 'updated_by_id', None):
                            obj.updated_by = acting_user
                            changed = True
                        if changed:
                            obj.save(update_fields=['received_by', 'received_by_display_name', 'confirmed_at', 'updated_by'])
                    
        except Exception as e:
            logger.exception("Unhandled error while updating hologram rolls details")


class HologramRequestViewSet(viewsets.ModelViewSet):
    queryset = HologramRequest.objects.all()
    serializer_class = HologramRequestSerializer
    permission_classes = [permissions.IsAuthenticated]

    def _build_production_updated_by_map(self, requests):
        """
        Build a mapping of HologramRequest -> officer display name who saved the fixed daily entry.
        """
        try:
            from django.db.models import Q
            from .models import DailyHologramRegister

            request_ids = []
            ref_nos = []
            for r in requests:
                if getattr(r, 'id', None) is not None:
                    request_ids.append(r.id)
                ref = str(getattr(r, 'ref_no', '') or '').strip()
                if ref:
                    ref_nos.append(ref)

            if not request_ids and not ref_nos:
                return {'by_request_id': {}, 'by_ref_no': {}}

            entries = (
                DailyHologramRegister.objects.filter(is_fixed=True)
                .filter(Q(hologram_request_id__in=request_ids) | Q(reference_no__in=ref_nos))
                .select_related('approved_by')
                .order_by('-approved_at', '-id')
            )

            by_request_id = {}
            by_ref_no = {}

            for entry in entries:
                display = str(getattr(entry, 'approved_by_display_name', '') or '').strip()
                if not display:
                    display = _get_user_display_name(getattr(entry, 'approved_by', None))
                if not display:
                    continue

                req_id = getattr(entry, 'hologram_request_id', None)
                if req_id is not None and req_id not in by_request_id:
                    by_request_id[req_id] = display

                ref = str(getattr(entry, 'reference_no', '') or '').strip()
                if ref and ref not in by_ref_no:
                    by_ref_no[ref] = display

            return {'by_request_id': by_request_id, 'by_ref_no': by_ref_no}
        except Exception:
            logger.exception("Failed to build production_updated_by map")
            return {'by_request_id': {}, 'by_ref_no': {}}

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())

        production_updated_by_map = self._build_production_updated_by_map(queryset)
        ctx = dict(self.get_serializer_context() or {})
        ctx['production_updated_by_map'] = production_updated_by_map

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True, context=ctx)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True, context=ctx)
        return Response(serializer.data)
    
    def allocate_holograms_fifo(self, roll, quantity_needed, reference_no, usage_date=None):
        """
        Allocate holograms from a roll using FIFO (First In, First Out) principle.
        
        Args:
            roll: HologramRollsDetails instance
            quantity_needed: Number of holograms to allocate
            reference_no: Reference number for the allocation
            usage_date: Usage date for the allocation
        
        Returns:
            Dict with allocation details: {'success': bool, 'allocated_ranges': list, 'message': str}
        """
        from models.transactional.supply_chain.hologram.models import HologramSerialRange
        
        
        # Get all available ranges ordered by from_serial (FIFO)
        available_ranges = HologramSerialRange.objects.filter(
            roll=roll,
            status='AVAILABLE'
        ).order_by('from_serial')  # CRITICAL: This ensures FIFO order
        
        
        # Check if we have enough inventory
        total_available = sum(r.count for r in available_ranges)
        if total_available < quantity_needed:
            return {
                'success': False,
                'allocated_ranges': [],
                'message': f'Insufficient inventory. Available: {total_available}, Needed: {quantity_needed}'
            }
        
        allocated_ranges = []
        remaining_needed = quantity_needed
        
        # Allocate from earliest ranges first (FIFO)
        for avail_range in available_ranges:
            if remaining_needed <= 0:
                break
                
            range_from = int(avail_range.from_serial)
            range_to = int(avail_range.to_serial)
            range_count = avail_range.count
            
            if remaining_needed >= range_count:
                # Take the entire range
                allocated_ranges.append({
                    'from': range_from,
                    'to': range_to,
                    'count': range_count,
                    'range_obj': avail_range
                })
                remaining_needed -= range_count
                
            else:
                # Take partial range from the beginning (FIFO)
                allocated_to = range_from + remaining_needed - 1
                allocated_ranges.append({
                    'from': range_from,
                    'to': allocated_to,
                    'count': remaining_needed,
                    'range_obj': avail_range
                })
                remaining_needed = 0
        
        # Apply allocation to database
        for alloc in allocated_ranges:
            avail_range = alloc['range_obj']
            alloc_from = alloc['from']
            alloc_to = alloc['to']
            alloc_count = alloc['count']
            
            avail_from = int(avail_range.from_serial)
            avail_to = int(avail_range.to_serial)
            
            if avail_from == alloc_from and avail_to == alloc_to:
                # Exact match - convert entire range to IN_USE
                avail_range.status = 'IN_USE'
                avail_range.used_date = usage_date
                avail_range.reference_no = reference_no
                avail_range.description = f'Allocated for request {reference_no}'
                avail_range.save()
                
            elif avail_from == alloc_from and alloc_to < avail_to:
                # Allocated from start - split into IN_USE and AVAILABLE
                # Create IN_USE range
                HologramSerialRange.objects.create(
                    roll=roll,
                    from_serial=str(alloc_from),
                    to_serial=str(alloc_to),
                    count=alloc_count,
                    status='IN_USE',
                    used_date=usage_date,
                    reference_no=reference_no,
                    description=f'Allocated for request {reference_no}'
                )
                # Update original to remaining AVAILABLE range
                avail_range.from_serial = str(alloc_to + 1)
                avail_range.count = avail_to - alloc_to
                avail_range.save()
                
            elif avail_from < alloc_from and alloc_to == avail_to:
                # Allocated from middle to end - split into AVAILABLE and IN_USE
                # Create IN_USE range
                HologramSerialRange.objects.create(
                    roll=roll,
                    from_serial=str(alloc_from),
                    to_serial=str(alloc_to),
                    count=alloc_count,
                    status='IN_USE',
                    used_date=usage_date,
                    reference_no=reference_no,
                    description=f'Allocated for request {reference_no}'
                )
                # Update original to remaining AVAILABLE range
                avail_range.to_serial = str(alloc_from - 1)
                avail_range.count = alloc_from - 1 - avail_from + 1
                avail_range.save()
                
            elif avail_from < alloc_from and alloc_to < avail_to:
                # Allocated from middle - split into 3 parts: AVAILABLE, IN_USE, AVAILABLE
                # Create IN_USE range
                HologramSerialRange.objects.create(
                    roll=roll,
                    from_serial=str(alloc_from),
                    to_serial=str(alloc_to),
                    count=alloc_count,
                    status='IN_USE',
                    used_date=usage_date,
                    reference_no=reference_no,
                    description=f'Allocated for request {reference_no}'
                )
                # Create second AVAILABLE range (after allocated)
                HologramSerialRange.objects.create(
                    roll=roll,
                    from_serial=str(alloc_to + 1),
                    to_serial=str(avail_to),
                    count=avail_to - alloc_to,
                    status='AVAILABLE',
                    description=f'Remaining range after allocation'
                )
                # Update original to first AVAILABLE range (before allocated)
                avail_range.to_serial = str(alloc_from - 1)
                avail_range.count = alloc_from - 1 - avail_from + 1
                avail_range.save()
        
        # Update the roll's available_range field
        roll.update_available_range()
        
        return {
            'success': True,
            'allocated_ranges': allocated_ranges,
            'message': f'Successfully allocated {quantity_needed} holograms using FIFO'
        }

    def get_queryset(self):
        user = self.request.user
        queryset = super().get_queryset()
        
        if not user.is_authenticated:
            return queryset.none()
            
        role_name = _normalize_role_name(getattr(getattr(user, 'role', None), 'name', ''))

        if _is_scoped_officer_or_licensee(role_name):
            scoped_by_request_license = scope_by_profile_or_workflow(
                user=user,
                queryset=queryset,
                workflow_id=WORKFLOW_IDS['HOLOGRAM_REQUEST'],
                licensee_field='license_id'
            )
            # Backward compatibility for historical rows without license_id populated.
            scoped_by_profile_license = scope_by_profile_or_workflow(
                user=user,
                queryset=queryset,
                workflow_id=WORKFLOW_IDS['HOLOGRAM_REQUEST'],
                licensee_field='licensee__licensee_id'
            )
            return queryset.filter(
                models.Q(id__in=scoped_by_request_license.values('id')) |
                models.Q(id__in=scoped_by_profile_license.values('id'))
            ).distinct()

        visible_stage_ids = _get_visible_stage_ids_for_user(
            user=user,
            workflow_id=WORKFLOW_IDS['HOLOGRAM_REQUEST']
        )
        if visible_stage_ids:
            return queryset.filter(current_stage_id__in=visible_stage_ids)
            
        return queryset.none()

    def perform_create(self, serializer):
        profile = _get_or_create_active_supply_chain_profile(self.request.user)
        if not profile:
            raise serializers.ValidationError({
                'detail': 'No active supply chain profile found. Select your manufacturing unit first.'
            })
        
        with db_transaction.atomic():
            ref_no = _generate_hologram_ref_no(HologramRequest)

            try:
                workflow = Workflow.objects.get(id=WORKFLOW_IDS['HOLOGRAM_REQUEST'])
                initial_stage = WorkflowStage.objects.get(workflow=workflow, is_initial=True)
            except Workflow.DoesNotExist:
                raise serializers.ValidationError("Workflow configuration missing.")

            instance = serializer.save(
                ref_no=ref_no,
                licensee=profile,
                license_id=_resolve_request_license_id(profile=profile, acting_user=self.request.user) or None,
                workflow=workflow,
                current_stage=initial_stage
            )

            Transaction.objects.create(
                application=instance,
                stage=initial_stage,
                performed_by=self.request.user,
                remarks='Hologram Production Request Submitted'
            )

    @action(detail=True, methods=['post'])
    def perform_action(self, request, pk=None):
        instance = self.get_object()
        action_name = request.data.get('action')
        remarks = request.data.get('remarks', '')
        issued_assets = request.data.get('issued_assets')

        if not getattr(instance, 'license_id', None):
            resolved_license_id = _resolve_request_license_id(
                profile=getattr(instance, 'licensee', None),
                acting_user=request.user
            )
            if resolved_license_id:
                instance.license_id = resolved_license_id
                instance.save(update_fields=['license_id'])

        
        # This ensures the frontend-provided ranges are preserved exactly as sent
        if issued_assets:
            # Create a deep copy to preserve original ranges
            import copy
            original_assets = copy.deepcopy(issued_assets)
            
            instance.issued_assets = original_assets
            instance.rolls_assigned = original_assets  # Save for "Currently Issued Holograms" tab
            instance.save()
        
        if not action_name:
            return Response({'error': 'Action is required'}, status=status.HTTP_400_BAD_REQUEST)

        normalized_action = str(action_name or '').strip().lower()
        if normalized_action in {'issue', 'approve'}:
            today = timezone.localdate()
            if instance.usage_date != today:
                return Response(
                    {
                        'error': f"Allocation can be approved only on the usage date ({instance.usage_date.strftime('%d-%m-%Y')})."
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )

        transitions = WorkflowTransition.objects.filter(
            workflow=instance.workflow,
            from_stage=instance.current_stage
        )
        
        
        selected_transition = None
        for t in transitions:
            cond = t.condition or {}
            cond_action = str(cond.get('action') or '').lower()
            role_ok = _condition_role_matches(cond, request.user)
            action_ok = cond_action == str(action_name).lower()
            if role_ok and action_ok:
                selected_transition = t
                break
        
        if not selected_transition:
             return Response({'error': 'Invalid action for current stage'}, status=status.HTTP_400_BAD_REQUEST)
        
        with db_transaction.atomic():
            # Refresh to ensure latest state
            instance.refresh_from_db()
            
            # Verify we are still in the 'from_stage'
            if instance.current_stage != selected_transition.from_stage:
                # Stage drift detected; abort to avoid applying an invalid transition.
                logger.warning(
                    "Hologram transition aborted due to stage mismatch (instance_id=%s current_stage=%s expected_from=%s)",
                    getattr(instance, "id", None),
                    getattr(instance.current_stage, "id", None),
                    getattr(selected_transition.from_stage, "id", None),
                )
                return Response({'error': 'Stage changed, please retry.'}, status=status.HTTP_409_CONFLICT)
            
            instance.current_stage = selected_transition.to_stage
            instance.save()
            
            # Verify persistence
            instance.refresh_from_db()
            if instance.current_stage != selected_transition.to_stage:
                raise serializers.ValidationError("Database update failed")

            
            Transaction.objects.create(
                application=instance,
                stage=selected_transition.to_stage,
                performed_by=self.request.user,
                remarks=remarks or f"Action '{action_name}' performed"
            )

            # CRITICAL: Dynamic Inventory Update
            # If assets were issued (e.g. on approval), update their status in Procurement inventory
            if issued_assets:
                self._update_inventory_status(instance, issued_assets)
                # Note: rolls_assigned was already saved above before any processing
            
        return Response(self.get_serializer(instance).data)

    def _update_inventory_status(self, request_instance, issued_assets):
        """
        Updates the status AND QUANTITY of allocated cartons in HologramProcurement
        """
        try:
            licensee = request_instance.licensee
            
            # Fetch all active procurements for this licensee to search within
            procurements = HologramProcurement.objects.filter(
                licensee=licensee
            ).all() 
            
            affected_procurements = {} # Map id -> instance
            
            for asset in issued_assets:
                cartoon_number = asset.get('cartoonNumber') or asset.get('cartoon_number')
                allocated_qty = int(asset.get('count') or asset.get('quantity') or 0)
                
                if not cartoon_number:
                    continue
                    
                # Find the procurement containing this cartoon
                found = False
                for proc in procurements:
                    carton_details = proc.carton_details or []
                    updated = False
                    
                    for detail in carton_details:
                        d_cartoon_num = detail.get('cartoon_number') or detail.get('cartoonNumber')
                        
                        if d_cartoon_num == cartoon_number:
                            # Found the carton! Update status and quantity.
                            current_status = detail.get('status', 'AVAILABLE')
                            current_available = int(detail.get('available_qty') if detail.get('available_qty') is not None else (detail.get('numberOfHolograms') or detail.get('total_count') or 0))
                            
                            
                            # Deduct allocated quantity OR use provided remaining
                            # Check both camelCase and snake_case formats
                            remaining_arg = asset.get('remainingInCartoon') or asset.get('remaining_in_cartoon')
                            
                            if remaining_arg is not None:
                                new_available = int(remaining_arg)
                            else:
                                new_available = max(0, current_available - allocated_qty)
                                
                            detail['available_qty'] = new_available
                            
                            # Update status if needed
                            if current_status != 'IN_USE':
                                detail['status'] = 'IN_USE'
                            
                            # Mark procurement as updated
                            updated = True
                            
                            found = True
                            break 
                    
                    if updated:
                        proc.carton_details = carton_details # Force assignment to trigger save
                        affected_procurements[proc.id] = proc
                    
                    if found:
                        break # Done with this asset
            
            # Bulk save affected procurements
            for proc in affected_procurements.values():
                # Sync quantity changes to HologramRollsDetails
                try:
                    for asset in issued_assets:
                        c_num = asset.get('cartoonNumber') or asset.get('cartoon_number')
                        a_qty = int(asset.get('count') or asset.get('quantity') or 0)

                        if not c_num:
                            continue

                        try:
                            roll_obj = HologramRollsDetails.objects.get(
                                procurement=proc,
                                carton_number=c_num
                            )
                        except HologramRollsDetails.DoesNotExist:
                            continue

                        # Resync from the procurement details to be 100% sure
                        target_detail = next(
                            (d for d in proc.carton_details if (d.get('cartoon_number') == c_num or d.get('cartoonNumber') == c_num)),
                            None
                        )

                        if target_detail:
                            roll_obj.available = target_detail['available_qty']
                            roll_obj.status = target_detail['status']
                            roll_obj.save()

                            # CRITICAL FIX: Trust frontend allocation if valid ranges are provided
                            # Only use FIFO as fallback if frontend didn't provide ranges
                            from_serial = asset.get('fromSerial') or asset.get('from_serial')
                            to_serial = asset.get('toSerial') or asset.get('to_serial')
                            a_qty = asset.get('quantity') or asset.get('count', 0)

                            if a_qty > 0:
                                from models.transactional.supply_chain.hologram.models import HologramSerialRange

                                # Check if frontend provided valid serial ranges
                                if from_serial and to_serial:
                                    # Trust the frontend allocation - just mark the range as IN_USE
                                    try:
                                        # Use FIFO to properly split ranges in the database
                                        allocation_result = self.allocate_holograms_fifo(
                                            roll=roll_obj,
                                            quantity_needed=a_qty,
                                            reference_no=request_instance.ref_no,
                                            usage_date=request_instance.usage_date if hasattr(request_instance, 'usage_date') else None
                                        )

                                        if allocation_result.get('success'):
                                            # CRITICAL FIX: Don't overwrite frontend ranges!
                                            # Keep the frontend-provided ranges in the response
                                            pass
                                        else:
                                            # Fallback: Create IN_USE entry with frontend ranges
                                            try:
                                                from_num = int(from_serial)
                                                to_num = int(to_serial)
                                                allocated_count = to_num - from_num + 1

                                                HologramSerialRange.objects.get_or_create(
                                                    roll=roll_obj,
                                                    from_serial=from_serial,
                                                    to_serial=to_serial,
                                                    defaults={
                                                        'count': allocated_count,
                                                        'status': 'IN_USE',
                                                        'used_date': request_instance.usage_date if hasattr(request_instance, 'usage_date') else None,
                                                        'reference_no': request_instance.ref_no,
                                                        'description': f'Allocated for request {request_instance.ref_no} (frontend ranges)'
                                                    }
                                                )
                                                roll_obj.update_available_range()
                                            except (ValueError, TypeError):
                                                logger.warning(
                                                    "Invalid frontend serial range (from=%s to=%s) for request=%s",
                                                    from_serial,
                                                    to_serial,
                                                    getattr(request_instance, "ref_no", None),
                                                )
                                    except Exception:
                                        logger.exception(
                                            "Error allocating hologram serial ranges (request=%s roll=%s)",
                                            getattr(request_instance, "ref_no", None),
                                            getattr(roll_obj, "id", None),
                                        )
                                else:
                                    # No ranges provided by frontend - use FIFO to calculate
                                    allocation_result = self.allocate_holograms_fifo(
                                        roll=roll_obj,
                                        quantity_needed=a_qty,
                                        reference_no=request_instance.ref_no,
                                        usage_date=request_instance.usage_date if hasattr(request_instance, 'usage_date') else None
                                    )

                                    if allocation_result.get('success'):
                                        # Update the asset with FIFO-calculated ranges
                                        if allocation_result.get('allocated_ranges'):
                                            first_range = allocation_result['allocated_ranges'][0]
                                            last_range = allocation_result['allocated_ranges'][-1]

                                            asset['fromSerial'] = str(first_range['from'])
                                            asset['toSerial'] = str(last_range['to'])
                                            asset['from_serial'] = str(first_range['from'])
                                            asset['to_serial'] = str(last_range['to'])
                                    else:
                                        logger.warning(
                                            "FIFO allocation failed for request=%s roll=%s quantity=%s",
                                            getattr(request_instance, "ref_no", None),
                                            getattr(roll_obj, "id", None),
                                            a_qty,
                                        )
                            else:
                                logger.debug(
                                    "Skipping allocation for non-positive quantity (request=%s roll=%s qty=%s)",
                                    getattr(request_instance, "ref_no", None),
                                    getattr(roll_obj, "id", None),
                                    a_qty,
                                )

                except Exception:
                    logger.exception(
                        "Error syncing hologram rolls details (procurement_id=%s)",
                        getattr(proc, "id", None),
                    )

        except Exception:
            logger.exception("Unhandled error during inventory status update")


from .models import DailyHologramRegister
from .serializers import DailyHologramRegisterSerializer, HologramRollsDetailsSerializer

def _get_user_display_name(user) -> str:
    """Return a human-readable display name for a user (first/middle/last, fallback to username)."""
    if user is None:
        return 'System'
    first = (getattr(user, 'first_name', '') or '').strip()
    middle = (getattr(user, 'middle_name', '') or '').strip()
    last = (getattr(user, 'last_name', '') or '').strip()
    parts = [p for p in [first, middle, last] if p]
    full = ' '.join(parts)
    return full if full else (getattr(user, 'username', None) or 'System')

class DailyHologramRegisterViewSet(viewsets.ModelViewSet):
    queryset = DailyHologramRegister.objects.all()  # FIXED: was 'dataset' which DRF ignores
    serializer_class = DailyHologramRegisterSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if not user.is_authenticated:
            return DailyHologramRegister.objects.none()
            
        role_name = _normalize_role_name(getattr(getattr(user, 'role', None), 'name', ''))
        
        # OIC / Licensee Access - Return entries for their licensee profile
        # Also support OIC roles which may use fallback profile
        if _is_scoped_officer_or_licensee(role_name):
            scoped_by_daily_license = scope_by_profile_or_workflow(
                user=user,
                queryset=DailyHologramRegister.objects.all(),
                workflow_id=WORKFLOW_IDS['HOLOGRAM_REQUEST'],
                licensee_field='license_id'
            )
            # Backward compatibility for old rows without daily.license_id populated.
            scoped_by_profile_license = scope_by_profile_or_workflow(
                user=user,
                queryset=DailyHologramRegister.objects.all(),
                workflow_id=WORKFLOW_IDS['HOLOGRAM_REQUEST'],
                licensee_field='licensee__licensee_id'
            )
            return DailyHologramRegister.objects.filter(
                models.Q(id__in=scoped_by_daily_license.values('id')) |
                models.Q(id__in=scoped_by_profile_license.values('id'))
            ).distinct()
                
        # IT Cell / Admin / OIC Access (View All)
        if _get_user_role_id(user) and StagePermission.objects.filter(
            role_id=_get_user_role_id(user),
            can_process=True,
            stage__workflow_id__in=[WORKFLOW_IDS['HOLOGRAM_PROCUREMENT'], WORKFLOW_IDS['HOLOGRAM_REQUEST']]
        ).exists():
             return DailyHologramRegister.objects.all()
             
        return DailyHologramRegister.objects.none()

    def perform_create(self, serializer):
        try:
            save_kwargs = {}
            # Daily register "Save" from OIC should be treated as approved entry metadata-wise.
            is_fixed_payload = bool(self.request.data.get('is_fixed', False))
            if is_fixed_payload:
                save_kwargs.update({
                    'approval_status': DailyHologramRegister.APPROVAL_STATUS_APPROVED,
                    'approved_by': self.request.user,
                    'approved_by_display_name': _get_user_display_name(self.request.user),
                    'approved_at': timezone.now()
                })

            # Ensure licensee is set from the logged-in user
            if hasattr(self.request.user, 'supply_chain_profile'):
                try:
                    profile = self.request.user.supply_chain_profile
                    instance = serializer.save(
                        licensee=profile,
                        license_id=_resolve_request_license_id(profile=profile, acting_user=self.request.user) or None,
                        **save_kwargs
                    )
                except Exception as e:
                    raise serializers.ValidationError(f"User profile error: {str(e)}")
            else:
                # DEBUG fallback
                # if self.request.user.is_superuser: # Unblock for now
                if True:
                    from models.masters.supply_chain.profile.models import SupplyChainUserProfile
                    first_profile = SupplyChainUserProfile.objects.first()
                    if first_profile:
                        instance = serializer.save(
                            licensee=first_profile,
                            license_id=_resolve_request_license_id(profile=first_profile, acting_user=self.request.user) or None,
                            **save_kwargs
                        )
                    else:
                        raise serializers.ValidationError("No profile found.")
                
            # CRITICAL: Update Procurement Inventory
            self._update_procurement_usage(instance)
            self._sync_brand_warehouse_stock(instance)
            
            # CRITICAL: Move linked request using workflow transition graph (DB-driven).
            if instance.hologram_request:
                try:
                    req = instance.hologram_request
                    moved_to = _apply_transition_by_action(
                        instance=req,
                        acting_user=self.request.user,
                        action_name='complete',
                        remarks='Hologram Production Completed via Daily Register'
                    )
                    if moved_to:
                        logger.debug(
                            "Hologram request transitioned via daily register (request_id=%s stage=%s)",
                            getattr(req, "id", None),
                            getattr(moved_to, "name", None) if moved_to else None,
                        )
                except Exception as e:
                    logger.exception(
                        "Failed to transition hologram request via daily register (request_id=%s)",
                        getattr(instance.hologram_request, "id", None),
                    )
            else:
                # FALLBACK: Try to find request by reference number
                try:
                    if instance.reference_no:
                        req = HologramRequest.objects.filter(ref_no=instance.reference_no).first()
                        if req:
                            # Link the entry to the request
                            instance.hologram_request = req
                            instance.save(update_fields=['hologram_request'])
                            
                            moved_to = _apply_transition_by_action(
                                instance=req,
                                acting_user=self.request.user,
                                action_name='complete',
                                remarks='Hologram Production Completed via Daily Register'
                            )
                            if moved_to:
                                logger.debug(
                                    "Hologram request transitioned via fallback ref_no (request_id=%s stage=%s)",
                                    getattr(req, "id", None),
                                    getattr(moved_to, "name", None) if moved_to else None,
                                )
                        else:
                            logger.info(
                                "No hologram request found for reference_no=%s during daily register save",
                                instance.reference_no,
                            )
                except Exception as e:
                    logger.exception(
                        "Fallback hologram request transition failed (reference_no=%s)",
                        getattr(instance, "reference_no", None),
                    )
            
        except Exception as e:
            logger.exception("Unhandled error during DailyHologramRegister create")
            raise serializers.ValidationError(f"Internal Server Error during save: {str(e)}")

    def perform_update(self, serializer):
        instance = serializer.save()
        # Keep officer name visible for edited fixed entries as well.
        if bool(getattr(instance, 'is_fixed', False)):
            needs_approval_meta = not getattr(instance, 'approved_by_id', None)
            needs_display_name = not str(getattr(instance, 'approved_by_display_name', '') or '').strip()
            if needs_approval_meta or needs_display_name:
                instance.approval_status = DailyHologramRegister.APPROVAL_STATUS_APPROVED
                instance.approved_by = instance.approved_by or self.request.user
                instance.approved_by_display_name = _get_user_display_name(instance.approved_by)
                instance.approved_at = instance.approved_at or timezone.now()
                instance.save(update_fields=['approval_status', 'approved_by', 'approved_by_display_name', 'approved_at'])
        self._sync_brand_warehouse_stock(instance)

    def _sync_brand_warehouse_stock(self, instance):
        """
        Ensure stock inventory and arrival trail are updated immediately
        when a Daily Register row is saved/fixed.
        """
        try:
            if not instance:
                return
            if not bool(getattr(instance, 'is_fixed', False)):
                return
            if int(getattr(instance, 'issued_qty', 0) or 0) <= 0:
                return
            if bool(getattr(instance, 'stock_updated', False)):
                return

            from models.transactional.supply_chain.brand_warehouse.services import BrandWarehouseStockService

            success = BrandWarehouseStockService.update_stock_from_hologram_register(instance)
            if success:
                DailyHologramRegister.objects.filter(id=instance.id).update(stock_updated=True)
        except Exception as e:
            logger.exception(
                "Failed to sync brand warehouse stock from daily hologram register (id=%s)",
                getattr(instance, "id", None),
            )

    def _update_procurement_usage(self, instance):
        """
        Wrapper to ensure atomic transaction and row locking.
        """
        with db_transaction.atomic():
            self._update_procurement_usage_impl(instance)

    def _update_procurement_usage_impl(self, instance):
        """
        Updates the usage and available quantity in the original HologramProcurement
        based on the DailyHologramRegister entry.
        Also updates usage_history JSON and creates HologramSerialRange records.
        """
        
        try:
            def _safe_int(value):
                try:
                    return int(value)
                except (TypeError, ValueError):
                    return None

            def _range_quantity(range_item):
                qty = _safe_int(range_item.get('quantity'))
                if qty is not None and qty >= 0:
                    return qty
                from_s = _safe_int(range_item.get('fromSerial') or range_item.get('from_serial'))
                to_s = _safe_int(range_item.get('toSerial') or range_item.get('to_serial'))
                if from_s is None or to_s is None:
                    return 0
                return max(0, to_s - from_s + 1)

            def _total_from_ranges(ranges):
                if not isinstance(ranges, list):
                    return 0
                return sum(_range_quantity(item or {}) for item in ranges)

            carton_number = None
            # Extract carton number strictly
            # roll_range format usually "CARTON - Range X-Y" or "CARTON-X-Y"
            if instance.roll_range:
                # CRITICAL FIX: Handle multi-brand format like "a2_BRAND_1", "a2_BRAND_2"
                # Extract the base carton number before any "_BRAND_" suffix
                roll_range_str = instance.roll_range.strip()
                
                # Check if this is a multi-brand format
                if '_BRAND_' in roll_range_str:
                    # Multi-brand format: 'a1 - 1 - 50_BRAND_1'
                    # Extract the base part before '_BRAND_' and then get the first element (carton number)
                    parts = roll_range_str.split('_BRAND_')
                    base_range = parts[0].strip()  # 'a1 - 1 - 50'
                    # Now extract just the carton number (first part before ' - ')
                    carton_number = base_range.split(' - ')[0].strip()  # 'a1'
                # Try splitting by " - " first (standard format)
                elif ' - ' in roll_range_str:
                    parts = roll_range_str.split(' - ')
                    carton_number = parts[0].strip()
                # Fallback: try splitting by "-" if no spaces found (e.g. "a2-51-100")
                elif '-' in roll_range_str:
                    parts = roll_range_str.split('-')
                    carton_number = parts[0].strip()
                # Fallback: just use the whole string if no separators
                else:
                    carton_number = roll_range_str
            
            if not carton_number:
                return


            # Find matching procurement
            from .models import HologramProcurement
            procurements = HologramProcurement.objects.filter(
                models.Q(licensee=instance.licensee) |
                models.Q(license_id=getattr(instance, 'license_id', None)) |
                models.Q(ref_no=getattr(instance, 'reference_no', None))
            ).distinct()
            
            target_procurement = None
            target_detail_index = -1
            
            # Normalization helper
            def normalize(s): return str(s).upper().strip().replace(' ', '')
            target_key = normalize(carton_number)

            for proc in procurements:
                details = proc.carton_details or []
                for idx, detail in enumerate(details):
                    d_carton = detail.get('cartoonNumber') or detail.get('cartoon_number') or detail.get('carton_number')
                    if normalize(d_carton) == target_key:
                        target_procurement = proc
                        target_detail_index = idx
                        break
                if target_procurement:
                    break

            # Fallback: resolve procurement from rolls table when carton_details JSON shape is inconsistent
            if not target_procurement:
                candidate_roll = None
                roll_fallback_qs = HologramRollsDetails.objects.select_related('procurement').all()
                if getattr(instance, 'license_id', None):
                    roll_fallback_qs = roll_fallback_qs.filter(
                        models.Q(license_id=instance.license_id) |
                        models.Q(procurement__license_id=instance.license_id)
                    )
                elif instance.licensee_id:
                    roll_fallback_qs = roll_fallback_qs.filter(procurement__licensee=instance.licensee)

                for roll_candidate in roll_fallback_qs:
                    if normalize(getattr(roll_candidate, 'carton_number', '')) == target_key:
                        candidate_roll = roll_candidate
                        break

                if candidate_roll and candidate_roll.procurement_id:
                    target_procurement = candidate_roll.procurement
                    details = target_procurement.carton_details or []
                    for idx, detail in enumerate(details):
                        d_carton = detail.get('cartoonNumber') or detail.get('cartoon_number') or detail.get('carton_number')
                        if normalize(d_carton) == target_key:
                            target_detail_index = idx
                            break
             
            if target_procurement:
                detail = {}
                if target_detail_index >= 0:
                    detail = target_procurement.carton_details[target_detail_index]
                
                # Get HologramRollsDetails object
                roll_obj = None
                try:
                    roll_obj = HologramRollsDetails.objects.select_for_update().filter(
                        procurement=target_procurement,
                        carton_number__iexact=(carton_number or '').strip()
                    ).first()

                    # Fallback for legacy rows with inconsistent spacing/casing.
                    if not roll_obj:
                        for candidate_roll in HologramRollsDetails.objects.select_for_update().filter(procurement=target_procurement):
                            if normalize(getattr(candidate_roll, 'carton_number', '')) == target_key:
                                roll_obj = candidate_roll
                                break

                    # Cross-procurement fallback when request/profile linkage differs but license/carton match.
                    if not roll_obj:
                        roll_cross_qs = HologramRollsDetails.objects.select_for_update().filter(
                            carton_number__iexact=(carton_number or '').strip()
                        )
                        if getattr(instance, 'license_id', None):
                            roll_cross_qs = roll_cross_qs.filter(
                                models.Q(license_id=instance.license_id) |
                                models.Q(procurement__license_id=instance.license_id)
                            )
                        elif instance.licensee_id:
                            roll_cross_qs = roll_cross_qs.filter(procurement__licensee=instance.licensee)
                        roll_obj = roll_cross_qs.first()

                except Exception:
                    roll_obj = None

                if not roll_obj:
                    return

                issued_ranges = instance.issued_ranges or []
                wastage_ranges = instance.wastage_ranges or []

                issued_qty_from_ranges = _total_from_ranges(issued_ranges)
                wastage_qty_from_ranges = _total_from_ranges(wastage_ranges)

                effective_issued_qty = _safe_int(instance.issued_qty) or 0
                effective_wastage_qty = _safe_int(instance.wastage_qty) or 0

                if issued_qty_from_ranges > 0:
                    effective_issued_qty = issued_qty_from_ranges
                if wastage_qty_from_ranges > 0:
                    effective_wastage_qty = wastage_qty_from_ranges
                
                # Get current counts
                total_count = roll_obj.total_count
                current_used = roll_obj.used
                current_damaged = roll_obj.damaged
                
                # Calculate new counts
                new_used = current_used + effective_issued_qty
                new_damaged = current_damaged + effective_wastage_qty
                new_available = max(0, total_count - new_used - new_damaged)
                
                
                # Update JSON in procurement
                updated_status = 'COMPLETED' if new_available == 0 else 'AVAILABLE'
                if target_detail_index >= 0:
                    detail['used_qty'] = new_used
                    detail['damage_qty'] = new_damaged
                    detail['available_qty'] = new_available
                    detail['status'] = updated_status
                    target_procurement.carton_details[target_detail_index] = detail 
                
                # Update balance
                deduct_qty = effective_issued_qty
                if target_procurement.local_qty > 0:
                     target_procurement.local_qty = max(0, float(target_procurement.local_qty) - deduct_qty)
                elif target_procurement.export_qty > 0:
                     target_procurement.export_qty = max(0, float(target_procurement.export_qty) - deduct_qty)
                elif target_procurement.defence_qty > 0:
                     target_procurement.defence_qty = max(0, float(target_procurement.defence_qty) - deduct_qty)
                
                target_procurement.save()
                
                # ===== NEW: Update HologramRollsDetails with usage_history =====
                
                # Initialize usage_history if not exists
                if not roll_obj.usage_history:
                    roll_obj.usage_history = []
                
                from .models import HologramSerialRange
                
                # SPECIAL CASE: "Not Used" - if issued and wastage are both 0
                if effective_issued_qty == 0 and effective_wastage_qty == 0:
                    
                    try:
                        start_int = None
                        end_int = None
                        
                        # PRIORITY 1: Use allocated_from_serial and allocated_to_serial if available
                        # These fields are sent by the frontend for "Not In Use" entries
                        if hasattr(instance, 'allocated_from_serial') and hasattr(instance, 'allocated_to_serial'):
                            if instance.allocated_from_serial and instance.allocated_to_serial:
                                try:
                                    start_int = int(instance.allocated_from_serial)
                                    end_int = int(instance.allocated_to_serial)
                                except (ValueError, TypeError):
                                    pass
                        
                        # FALLBACK: Use regex to extract range from roll_range string
                        if start_int is None or end_int is None:
                            import re
                            # Use regex to find all numbers in the string
                            # This handles "a2 - 51 - 100", "a1 - Range 1-50", "51-100", etc.
                            # We expect the last two numbers to be the start and end of the range
                            numbers = re.findall(r'\d+', instance.roll_range)
                            
                            if len(numbers) >= 2:
                                # Assume the last two numbers are the range
                                start_s = numbers[-2]
                                end_s = numbers[-1]
                                
                                start_int = int(start_s)
                                end_int = int(end_s)
                                
                        
                        if start_int is not None and end_int is not None:
                            # Fetch ALL IN_USE ranges for this roll
                            in_use_candidates = HologramSerialRange.objects.filter(roll=roll_obj, status='IN_USE')
                            
                            match_found = False
                            for candidate in in_use_candidates:
                                try:
                                    c_start = int(candidate.from_serial)
                                    c_end = int(candidate.to_serial)
                                    
                                    # Check for exact match OR overlap
                                    # We want to be generous here: if the candidate is fully contained in the target range, release it
                                    if c_start >= start_int and c_end <= end_int:
                                        candidate.status = 'AVAILABLE'
                                        candidate.description = f'Released from Not Used entry {instance.reference_no}'
                                        candidate.save()
                                        match_found = True
                                except ValueError:
                                    continue
                            
                            if not match_found:
                                logger.debug(
                                    "No IN_USE ranges matched for release (request=%s roll=%s range=%s-%s)",
                                    getattr(instance, "reference_no", None),
                                    getattr(roll_obj, "id", None),
                                    start_int,
                                    end_int,
                                )
                        else:
                            logger.warning(
                                "Skipping release of ranges due to invalid range values (from=%s to=%s request=%s)",
                                start_s,
                                end_s,
                                getattr(instance, "reference_no", None),
                            )

                    except Exception as e:
                        logger.exception(
                            "Error releasing IN_USE ranges for request=%s roll=%s",
                            getattr(instance, "reference_no", None),
                            getattr(roll_obj, "id", None),
                        )

                # Check existing IN_USE ranges
                existing_in_use = HologramSerialRange.objects.filter(roll=roll_obj, status='IN_USE')
                
                # CRITICAL: Find and delete IN_USE ranges that will be split
                # Collect all serials that will be marked as USED or DAMAGED
                used_serials = set()
                damaged_serials = set()
                
                # Collect USED serials
                if effective_issued_qty > 0:
                    if issued_ranges:
                        for issued_range in issued_ranges:
                            from_s = issued_range.get('fromSerial') or issued_range.get('from_serial')
                            to_s = issued_range.get('toSerial') or issued_range.get('to_serial')
                            try:
                                from_num = int(from_s)
                                to_num = int(to_s)
                                for serial in range(from_num, to_num + 1):
                                    used_serials.add(serial)
                            except (ValueError, TypeError):
                                pass
                    else:
                        try:
                            from_num = int(instance.issued_from)
                            to_num = int(instance.issued_to)
                            for serial in range(from_num, to_num + 1):
                                used_serials.add(serial)
                        except (ValueError, TypeError):
                            pass
                
                # Collect DAMAGED serials
                if effective_wastage_qty > 0:
                    if wastage_ranges:
                        for wastage_range in wastage_ranges:
                            from_s = wastage_range.get('fromSerial') or wastage_range.get('from_serial')
                            to_s = wastage_range.get('toSerial') or wastage_range.get('to_serial')
                            try:
                                from_num = int(from_s)
                                to_num = int(to_s)
                                for serial in range(from_num, to_num + 1):
                                    damaged_serials.add(serial)
                            except (ValueError, TypeError):
                                pass
                    else:
                        try:
                            from_num = int(instance.wastage_from)
                            to_num = int(instance.wastage_to)
                            for serial in range(from_num, to_num + 1):
                                damaged_serials.add(serial)
                        except (ValueError, TypeError):
                            pass
                
                
                
                # CRITICAL FIX: Also collect used/damaged serials from ALL OTHER daily register entries for this same roll
                # This prevents duplicate AVAILABLE ranges in multi-brand scenarios
                other_entries = DailyHologramRegister.objects.filter(
                    cartoon_number=carton_number,
                    hologram_type=roll_obj.type
                ).exclude(id=instance.id)  # Exclude the current entry being saved
                
                
                for other_entry in other_entries:
                    # Collect USED serials from other entries
                    if other_entry.issued_qty and other_entry.issued_qty > 0:
                        other_issued_ranges = other_entry.issued_ranges or []
                        if other_issued_ranges:
                            for issued_range in other_issued_ranges:
                                from_s = issued_range.get('fromSerial') or issued_range.get('from_serial')
                                to_s = issued_range.get('toSerial') or issued_range.get('to_serial')
                                try:
                                    from_num = int(from_s)
                                    to_num = int(to_s)
                                    for serial in range(from_num, to_num + 1):
                                        used_serials.add(serial)
                                except (ValueError, TypeError):
                                    pass
                        else:
                            try:
                                from_num = int(other_entry.issued_from)
                                to_num = int(other_entry.issued_to)
                                for serial in range(from_num, to_num + 1):
                                    used_serials.add(serial)
                            except (ValueError, TypeError):
                                pass
                    
                    # Collect DAMAGED serials from other entries
                    if other_entry.wastage_qty and other_entry.wastage_qty > 0:
                        other_wastage_ranges = other_entry.wastage_ranges or []
                        if other_wastage_ranges:
                            for wastage_range in other_wastage_ranges:
                                from_s = wastage_range.get('fromSerial') or wastage_range.get('from_serial')
                                to_s = wastage_range.get('toSerial') or wastage_range.get('to_serial')
                                try:
                                    from_num = int(from_s)
                                    to_num = int(to_s)
                                    for serial in range(from_num, to_num + 1):
                                        damaged_serials.add(serial)
                                except (ValueError, TypeError):
                                    pass
                        else:
                            try:
                                from_num = int(other_entry.wastage_from)
                                to_num = int(other_entry.wastage_to)
                                for serial in range(from_num, to_num + 1):
                                    damaged_serials.add(serial)
                            except (ValueError, TypeError):
                                pass
                

                
                # Find IN_USE ranges that overlap with used/damaged serials
                in_use_ranges = HologramSerialRange.objects.filter(roll=roll_obj, status='IN_USE').order_by('from_serial')
                
                # Check for AVAILABLE ranges too - if we have them, we shouldn't run fallback
                available_ranges_check = HologramSerialRange.objects.filter(roll=roll_obj, status='AVAILABLE')
                
                if in_use_ranges.count() == 0 and available_ranges_check.count() == 0:
                    
                    # FALLBACK: If no IN_USE ranges exist, we need to infer the allocated range
                    # from the request's rolls_assigned data
                    
                    # Try to find the hologram request that was allocated
                    from .models import HologramRequest
                    try:
                        request = HologramRequest.objects.get(ref_no=instance.reference_no)
                        if request.rolls_assigned:
                            for assigned_roll in request.rolls_assigned:
                                if assigned_roll.get('cartoonNumber') == carton_number or assigned_roll.get('cartoon_number') == carton_number:
                                    # Found the allocated range
                                    alloc_from = assigned_roll.get('fromSerial') or assigned_roll.get('from_serial')
                                    alloc_to = assigned_roll.get('toSerial') or assigned_roll.get('to_serial')
                                    alloc_count = assigned_roll.get('count') or assigned_roll.get('quantity')
                                    
                                    
                                    # Create a virtual IN_USE range for processing
                                    try:
                                        alloc_from_num = int(alloc_from)
                                        alloc_to_num = int(alloc_to)
                                        
                                        # Calculate leftover serials
                                        allocated_serials = set(range(alloc_from_num, alloc_to_num + 1))
                                        leftover_serials = allocated_serials - used_serials - damaged_serials
                                        
                                        
                                        # Create AVAILABLE ranges for leftovers
                                        if leftover_serials:
                                            sorted_leftovers = sorted(leftover_serials)
                                            leftover_ranges = []
                                            current_start = sorted_leftovers[0]
                                            current_end = sorted_leftovers[0]
                                            
                                            for serial in sorted_leftovers[1:]:
                                                if serial == current_end + 1:
                                                    current_end = serial
                                                else:
                                                    leftover_ranges.append((current_start, current_end))
                                                    current_start = serial
                                                    current_end = serial
                                            leftover_ranges.append((current_start, current_end))
                                            
                                            
                                            for left_from, left_to in leftover_ranges:
                                                leftover_count = left_to - left_from + 1
                                                HologramSerialRange.objects.create(
                                                    roll=roll_obj,
                                                    from_serial=str(left_from),
                                                    to_serial=str(left_to),
                                                    count=leftover_count,
                                                    status='AVAILABLE',
                                                    description=f'Leftover from allocation {instance.reference_no}'
                                                )
                                        
                                    except (ValueError, TypeError) as e:
                                        logger.warning(
                                            "Invalid serial values during allocation cleanup (request=%s roll=%s)",
                                            getattr(instance, "reference_no", None),
                                            getattr(roll_obj, "id", None),
                                        )
                                    
                                    break
                    except HologramRequest.DoesNotExist:
                        logger.info(
                            "Hologram request not found while updating procurement usage (request_id=%s)",
                            getattr(instance, "hologram_request_id", None),
                        )
                
                for in_use_range in in_use_ranges:
                    try:
                        range_from = int(in_use_range.from_serial)
                        range_to = int(in_use_range.to_serial)
                        
                        # Check if this IN_USE range overlaps with used/damaged serials
                        range_serials = set(range(range_from, range_to + 1))
                        overlaps_used = bool(range_serials & used_serials)
                        overlaps_damaged = bool(range_serials & damaged_serials)
                        
                        if overlaps_used or overlaps_damaged:
                            
                            # Save reference_no before deleting
                            ref_no = in_use_range.reference_no or instance.reference_no
                            
                            # Delete the original IN_USE range - we'll recreate the pieces
                            in_use_range.delete()
                            
                            # Find leftover serials (not used and not damaged)
                            leftover_serials = range_serials - used_serials - damaged_serials
                            
                            
                            # Create AVAILABLE ranges for leftovers
                            if leftover_serials:
                                # Sort and group consecutive serials
                                sorted_leftovers = sorted(leftover_serials)
                                leftover_ranges = []
                                current_start = sorted_leftovers[0]
                                current_end = sorted_leftovers[0]
                                
                                for serial in sorted_leftovers[1:]:
                                    if serial == current_end + 1:
                                        current_end = serial
                                    else:
                                        leftover_ranges.append((current_start, current_end))
                                        current_start = serial
                                        current_end = serial
                                leftover_ranges.append((current_start, current_end))
                                
                                
                                # Create AVAILABLE range entries
                                for left_from, left_to in leftover_ranges:
                                    leftover_count = left_to - left_from + 1
                                    HologramSerialRange.objects.create(
                                        roll=roll_obj,
                                        from_serial=str(left_from),
                                        to_serial=str(left_to),
                                        count=leftover_count,
                                        status='AVAILABLE',
                                        description=f'Leftover from allocation {ref_no}'
                                    )
                            else:
                                logger.debug(
                                    "No leftover serials after splitting IN_USE range (request=%s roll=%s)",
                                    getattr(instance, "reference_no", None),
                                    getattr(roll_obj, "id", None),
                                )
                    
                    except (ValueError, TypeError) as e:
                        logger.warning(
                            "Invalid IN_USE range values encountered during split (roll=%s)",
                            getattr(roll_obj, "id", None),
                        )
                
                # CRITICAL FIX: Also process existing AVAILABLE ranges
                # This handles multi-brand scenarios where the first entry already converted IN_USE to AVAILABLE
                # and the second entry needs to mark some of those AVAILABLE serials as USED
                available_ranges = HologramSerialRange.objects.filter(roll=roll_obj, status='AVAILABLE').order_by('from_serial')
                
                for avail_range in available_ranges:
                    try:
                        range_from = int(avail_range.from_serial)
                        range_to = int(avail_range.to_serial)
                        
                        # Check if this AVAILABLE range overlaps with used/damaged serials
                        range_serials = set(range(range_from, range_to + 1))
                        overlaps_used = bool(range_serials & used_serials)
                        overlaps_damaged = bool(range_serials & damaged_serials)
                        
                        if overlaps_used or overlaps_damaged:
                            
                            # Delete the original AVAILABLE range - we'll recreate the pieces
                            avail_range.delete()
                            
                            # Find leftover serials (not used and not damaged)
                            leftover_serials = range_serials - used_serials - damaged_serials
                            
                            
                            # Create new AVAILABLE ranges for leftovers
                            if leftover_serials:
                                # Sort and group consecutive serials
                                sorted_leftovers = sorted(leftover_serials)
                                leftover_ranges = []
                                current_start = sorted_leftovers[0]
                                current_end = sorted_leftovers[0]
                                
                                for serial in sorted_leftovers[1:]:
                                    if serial == current_end + 1:
                                        current_end = serial
                                    else:
                                        leftover_ranges.append((current_start, current_end))
                                        current_start = serial
                                        current_end = serial
                                leftover_ranges.append((current_start, current_end))
                                
                                
                                # Create AVAILABLE range entries
                                for left_from, left_to in leftover_ranges:
                                    leftover_count = left_to - left_from + 1
                                    HologramSerialRange.objects.create(
                                        roll=roll_obj,
                                        from_serial=str(left_from),
                                        to_serial=str(left_to),
                                        count=leftover_count,
                                        status='AVAILABLE',
                                        description=f'Remaining after usage recorded'
                                    )
                            else:
                                logger.debug(
                                    "No leftover serials after splitting AVAILABLE range (roll=%s)",
                                    getattr(roll_obj, "id", None),
                                )
                    
                    except (ValueError, TypeError) as e:
                        logger.warning(
                            "Invalid AVAILABLE range values encountered during split (roll=%s)",
                            getattr(roll_obj, "id", None),
                        )

                
                # Now create USED ranges
                if effective_issued_qty > 0:
                    if issued_ranges:
                        for issued_range in issued_ranges:
                            current_range_qty = _range_quantity(issued_range or {})
                            usage_entry = {
                                'type': 'ISSUED',
                                'cartoonNumber': carton_number,
                                'issuedFromSerial': issued_range.get('fromSerial') or issued_range.get('from_serial'),
                                'issuedToSerial': issued_range.get('toSerial') or issued_range.get('to_serial'),
                                'issuedQuantity': current_range_qty,
                                'date': str(instance.usage_date),
                                'referenceNo': instance.reference_no,
                                'brandName': instance.brand_details,
                                'brandDetails': instance.brand_details,
                                'bottleSize': instance.bottle_size,
                                'approvedBy': _get_user_display_name(self.request.user) if self.request else 'System',
                                'approvedAt': timezone.now().isoformat()
                            }
                            roll_obj.usage_history.append(usage_entry)
                            
                            # Create USED range
                            HologramSerialRange.objects.create(
                                roll=roll_obj,
                                from_serial=usage_entry['issuedFromSerial'],
                                to_serial=usage_entry['issuedToSerial'],
                                count=current_range_qty,
                                status='USED',
                                used_date=instance.usage_date,
                                reference_no=instance.reference_no,
                                brand_name=instance.brand_details,
                                bottle_size=instance.bottle_size,
                                updated_by=self.request.user if self.request else None,
                                updated_by_display_name=_get_user_display_name(self.request.user) if self.request else None,
                                description=f"Used on {instance.usage_date}"
                            )
                    else:
                        # Legacy: single issued range
                        usage_entry = {
                            'type': 'ISSUED',
                            'cartoonNumber': carton_number,
                            'issuedFromSerial': instance.issued_from,
                            'issuedToSerial': instance.issued_to,
                            'issuedQuantity': effective_issued_qty,
                            'date': str(instance.usage_date),
                            'referenceNo': instance.reference_no,
                            'brandName': instance.brand_details,
                            'brandDetails': instance.brand_details,
                            'bottleSize': instance.bottle_size,
                            'approvedBy': _get_user_display_name(self.request.user) if self.request else 'System',
                            'approvedAt': timezone.now().isoformat()
                        }
                        roll_obj.usage_history.append(usage_entry)
                        
                        # Create USED range
                        HologramSerialRange.objects.create(
                            roll=roll_obj,
                            from_serial=instance.issued_from,
                            to_serial=instance.issued_to,
                            count=effective_issued_qty,
                            status='USED',
                            used_date=instance.usage_date,
                            reference_no=instance.reference_no,
                            brand_name=instance.brand_details,
                            bottle_size=instance.bottle_size,
                            updated_by=self.request.user if self.request else None,
                            updated_by_display_name=_get_user_display_name(self.request.user) if self.request else None,
                            description=f"Used on {instance.usage_date}"
                        )
                
                # Now create DAMAGED ranges
                if effective_wastage_qty > 0:
                    if wastage_ranges:
                        for wastage_range in wastage_ranges:
                            current_range_qty = _range_quantity(wastage_range or {})
                            usage_entry = {
                                'type': 'WASTAGE',
                                'cartoonNumber': carton_number,
                                'wastageFromSerial': wastage_range.get('fromSerial') or wastage_range.get('from_serial'),
                                'wastageToSerial': wastage_range.get('toSerial') or wastage_range.get('to_serial'),
                                'wastageQuantity': current_range_qty,
                                'date': str(instance.usage_date),
                                'damageReason': wastage_range.get('damageReason') or instance.damage_reason,
                                'referenceNo': instance.reference_no,
                                'brandName': instance.brand_details,
                                'brandDetails': instance.brand_details,
                                'reportedBy': _get_user_display_name(self.request.user) if self.request else 'System',
                                'approvedBy': _get_user_display_name(self.request.user) if self.request else 'System',
                                'approvedAt': timezone.now().isoformat()
                            }
                            roll_obj.usage_history.append(usage_entry)
                            
                            # Create DAMAGED range
                            HologramSerialRange.objects.create(
                                roll=roll_obj,
                                from_serial=usage_entry['wastageFromSerial'],
                                to_serial=usage_entry['wastageToSerial'],
                                count=current_range_qty,
                                status='DAMAGED',
                                damage_date=instance.usage_date,
                                damage_reason=usage_entry['damageReason'],
                                reported_by=_get_user_display_name(self.request.user) if self.request else 'System',
                                updated_by=self.request.user if self.request else None,
                                updated_by_display_name=_get_user_display_name(self.request.user) if self.request else None,
                                description=usage_entry['damageReason'] or 'Damaged during production'
                            )
                    else:
                        # Legacy: single wastage range
                        usage_entry = {
                            'type': 'WASTAGE',
                            'cartoonNumber': carton_number,
                            'wastageFromSerial': instance.wastage_from,
                            'wastageToSerial': instance.wastage_to,
                            'wastageQuantity': effective_wastage_qty,
                            'date': str(instance.usage_date),
                            'damageReason': instance.damage_reason,
                            'referenceNo': instance.reference_no,
                            'brandName': instance.brand_details,
                            'brandDetails': instance.brand_details,
                            'reportedBy': _get_user_display_name(self.request.user) if self.request else 'System',
                            'approvedBy': _get_user_display_name(self.request.user) if self.request else 'System',
                            'approvedAt': timezone.now().isoformat()
                        }
                        roll_obj.usage_history.append(usage_entry)
                        
                        # Create DAMAGED range
                        HologramSerialRange.objects.create(
                            roll=roll_obj,
                            from_serial=instance.wastage_from,
                            to_serial=instance.wastage_to,
                            count=effective_wastage_qty,
                            status='DAMAGED',
                            damage_date=instance.usage_date,
                            damage_reason=instance.damage_reason,
                            reported_by=_get_user_display_name(self.request.user) if self.request else 'System',
                            updated_by=self.request.user if self.request else None,
                            updated_by_display_name=_get_user_display_name(self.request.user) if self.request else None,
                            description=instance.damage_reason or 'Damaged during production'
                        )
                
                # Update HologramRollsDetails counts and save
                roll_obj.used = new_used
                roll_obj.damaged = new_damaged
                roll_obj.available = new_available
                roll_obj.status = updated_status
                roll_obj.save()
                # After Daily Register save, remaining IN_USE ranges should be released.
                # Status policy after save: only AVAILABLE or COMPLETED.
                remaining_in_use_ranges = HologramSerialRange.objects.filter(roll=roll_obj, status='IN_USE')
                if remaining_in_use_ranges.exists():
                    for in_use_range in remaining_in_use_ranges:
                        in_use_range.status = 'AVAILABLE'
                        if not in_use_range.description:
                            in_use_range.description = f"Released to AVAILABLE after daily save {instance.reference_no}"
                        in_use_range.save(update_fields=['status', 'description', 'updated_at'])

                # Recalculate available count from AVAILABLE ranges
                available_ranges = HologramSerialRange.objects.filter(roll=roll_obj, status='AVAILABLE')
                total_available = sum(r.count for r in available_ranges)
                if total_available != roll_obj.available:
                    roll_obj.available = total_available
                    roll_obj.save(update_fields=['available'])

                # Status rule after save:
                # available == 0 -> COMPLETED
                # available  > 0 -> AVAILABLE
                if roll_obj.available == 0:
                    roll_obj.status = 'COMPLETED'
                else:
                    roll_obj.status = 'AVAILABLE'

                roll_obj.save(update_fields=['status'])
                
                # CRITICAL FIX: Sync these changes back to the HologramProcurement JSON
                # This ensures that APIs reading from carton_details (JSON) see the same data as those reading from HologramRollsDetails (Table)
                try:
                    proc_to_update = roll_obj.procurement
                    # Reload procurement to get latest JSON
                    proc_to_update.refresh_from_db()
                    
                    if proc_to_update.carton_details:
                        json_updated = False
                        updated_details = proc_to_update.carton_details
                        
                        for d in updated_details:
                            d_c_num = d.get('cartoonNumber') or d.get('cartoon_number')
                            if d_c_num and str(d_c_num).strip().upper() == str(carton_number).strip().upper():
                                # Found the matching entry in JSON - update it!
                                d['available_qty'] = roll_obj.available
                                d['used_qty'] = roll_obj.used
                                d['damaged_qty'] = roll_obj.damaged
                                d['status'] = roll_obj.status
                                json_updated = True
                                break
                        
                        if json_updated:
                            proc_to_update.carton_details = updated_details
                            proc_to_update.save(update_fields=['carton_details'])
                except Exception as json_e:
                    logger.exception(
                        "Failed to sync carton_details JSON for roll=%s",
                        getattr(roll_obj, "id", None),
                    )
                
                # Update available_range to reflect new state
                roll_obj.update_available_range()
                
                # CRITICAL VERIFICATION: Check if leftover ranges were actually created
                final_available_ranges = HologramSerialRange.objects.filter(roll=roll_obj, status='AVAILABLE')
                
            else:
                logger.warning(
                    "Hologram roll not found while updating procurement usage (reference_no=%s carton_number=%s)",
                    getattr(instance, "reference_no", None),
                    carton_number,
                )
                
        except Exception as e:
            logger.exception("Unhandled error during procurement usage update")

class HologramRollsDetailsViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = HologramRollsDetails.objects.all()
    serializer_class = HologramRollsDetailsSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if not user.is_authenticated:
            return HologramRollsDetails.objects.none()
            
        role_name = _normalize_role_name(getattr(getattr(user, 'role', None), 'name', ''))
        
        # OIC / Licensee Access
        if _is_scoped_officer_or_licensee(role_name):
            scoped_by_roll_license = scope_by_profile_or_workflow(
                user=user,
                queryset=HologramRollsDetails.objects.all(),
                workflow_id=WORKFLOW_IDS['HOLOGRAM_PROCUREMENT'],
                licensee_field='license_id'
            )
            # Backward compatibility for historical rows without license_id populated.
            scoped_by_procurement = scope_by_profile_or_workflow(
                user=user,
                queryset=HologramRollsDetails.objects.all(),
                workflow_id=WORKFLOW_IDS['HOLOGRAM_PROCUREMENT'],
                licensee_field='procurement__licensee__licensee_id'
            )
            return HologramRollsDetails.objects.filter(
                models.Q(id__in=scoped_by_roll_license.values('id')) |
                models.Q(id__in=scoped_by_procurement.values('id'))
            ).distinct()
                
        # IT Cell / Admin / Commissioner / OIC Access (View All)
        if _get_user_role_id(user) and StagePermission.objects.filter(
            role_id=_get_user_role_id(user),
            can_process=True,
            stage__workflow_id__in=[WORKFLOW_IDS['HOLOGRAM_PROCUREMENT'], WORKFLOW_IDS['HOLOGRAM_REQUEST']]
        ).exists():
             return HologramRollsDetails.objects.all()
             
        return HologramRollsDetails.objects.none()
    
    def list(self, request, *args, **kwargs):
        """Override list to calculate and populate available_range for each roll"""
        
        queryset = self.filter_queryset(self.get_queryset())
        
        
        # Update available_range for all rolls in queryset
        roll_ids = []
        for roll in queryset:
            roll_ids.append(roll.id)
        
        # Refresh queryset to get updated values
        queryset = self.get_queryset().filter(id__in=roll_ids)
        
        
        # Now serialize and return
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
    
    def retrieve(self, request, *args, **kwargs):
        """Override retrieve to calculate and populate available_range"""
        instance = self.get_object()
        instance.update_available_range()
        serializer = self.get_serializer(instance)
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'])
    def serial_ranges(self, request, pk=None):
        """
        Get detailed serial ranges for a specific roll
        Returns ranges from HologramSerialRange table if available,
        otherwise generates from usage_history JSON
        """
        roll = self.get_object()
        
        # Try to get from HologramSerialRange table first
        from .models import HologramSerialRange
        from .serializers import HologramSerialRangeSerializer
        
        ranges = HologramSerialRange.objects.filter(roll=roll).order_by('from_serial')
        
        if ranges.exists():
            # Return from database table
            serializer = HologramSerialRangeSerializer(ranges, many=True)
            return Response({
                'source': 'database',
                'ranges': serializer.data,
                'total_count': ranges.count()
            })
        else:
            # Fallback: Generate from usage_history JSON
            usage_history = roll.usage_history or []
            serial_ranges = []
            
            # Calculate what serials have been used/damaged
            used_serials = set()
            
            for entry in usage_history:
                if entry.get('type') == 'ISSUED':
                    from_serial = entry.get('issuedFromSerial') or entry.get('fromSerial')
                    to_serial = entry.get('issuedToSerial') or entry.get('toSerial')
                    qty = entry.get('issuedQuantity') or entry.get('quantity') or 0
                    
                    if from_serial and to_serial:
                        # Extract numeric parts
                        from_num = self._extract_serial_number(from_serial)
                        to_num = self._extract_serial_number(to_serial)
                        
                        # Mark all serials in this range as used
                        for num in range(from_num, to_num + 1):
                            used_serials.add(num)
                    
                    serial_ranges.append({
                        'from_serial': from_serial,
                        'to_serial': to_serial,
                        'count': qty,
                        'status': 'USED',
                        'description': f"Used on {entry.get('date')}",
                        'used_date': entry.get('date'),
                        'reference_no': entry.get('referenceNo'),
                        'brand_name': entry.get('brandName'),
                        'bottle_size': entry.get('bottleSize'),
                        'brand_details': entry.get('brandDetails')
                    })
                    
                elif entry.get('type') in ['WASTAGE', 'DAMAGED']:
                    from_serial = entry.get('wastageFromSerial') or entry.get('fromSerial')
                    to_serial = entry.get('wastageToSerial') or entry.get('toSerial')
                    qty = entry.get('wastageQuantity') or entry.get('quantity') or 0
                    
                    if from_serial and to_serial:
                        # Extract numeric parts
                        from_num = self._extract_serial_number(from_serial)
                        to_num = self._extract_serial_number(to_serial)
                        
                        # Mark all serials in this range as damaged
                        for num in range(from_num, to_num + 1):
                            used_serials.add(num)
                    
                    serial_ranges.append({
                        'from_serial': from_serial,
                        'to_serial': to_serial,
                        'count': qty,
                        'status': 'DAMAGED',
                        'description': entry.get('damageReason') or 'Damaged',
                        'damage_date': entry.get('date'),
                        'damage_reason': entry.get('damageReason'),
                        'reported_by': entry.get('reportedBy') or entry.get('approvedBy')
                    })
            
            # Generate available range(s)
            if roll.available > 0:
                # Get the roll's full range
                from_num = self._extract_serial_number(roll.from_serial)
                to_num = self._extract_serial_number(roll.to_serial)
                prefix = roll.from_serial[:-len(str(from_num))] if from_num > 0 else roll.from_serial
                
                # Find available ranges (gaps in used_serials)
                available_ranges = []
                current_start = None
                
                for num in range(from_num, to_num + 1):
                    if num not in used_serials:
                        if current_start is None:
                            current_start = num
                    else:
                        if current_start is not None:
                            # End of available range
                            available_ranges.append({
                                'from': current_start,
                                'to': num - 1,
                                'count': num - current_start
                            })
                            current_start = None
                
                # Handle last range
                if current_start is not None:
                    available_ranges.append({
                        'from': current_start,
                        'to': to_num,
                        'count': to_num - current_start + 1
                    })
                
                # Add available ranges to response
                for avail_range in available_ranges:
                    from_serial = prefix + str(avail_range['from']).zfill(6)
                    to_serial = prefix + str(avail_range['to']).zfill(6)
                    
                    serial_ranges.append({
                        'from_serial': from_serial,
                        'to_serial': to_serial,
                        'count': avail_range['count'],
                        'status': 'AVAILABLE',
                        'description': 'Available for production use'
                    })
            
            return Response({
                'source': 'json',
                'ranges': serial_ranges,
                'total_count': len(serial_ranges)
            })
    
    def _extract_serial_number(self, serial: str) -> int:
        """Extract numeric part from serial string"""
        import re
        match = re.search(r'\d+$', serial or '')
        return int(match.group()) if match else 0




class CommissionerDashboardViewSet(viewsets.ViewSet):
    """
    ViewSet for Commissioner Dashboard - Track all hologram requests with complete flow
    """
    permission_classes = [permissions.IsAuthenticated]
    
    @action(detail=False, methods=['get'])
    def daily_register_overview(self, request):
        """
        Get complete overview of all hologram requests for commissioner dashboard
        Shows: Applied, Under Process, Completed On Time, Completed Late, Overdue
        """
        from django.db.models import Q
        from datetime import datetime, time
        from django.utils import timezone as django_timezone
        from models.masters.core.models import SupplyChainTimerConfig
        
        try:
            workflow_id = WORKFLOW_IDS['HOLOGRAM_REQUEST']
            request_transitions = WorkflowTransition.objects.filter(workflow_id=workflow_id).only('to_stage_id', 'condition')
            approval_to_stage_ids = set()
            reject_to_stage_ids = set()
            for transition in request_transitions:
                action_name = str((transition.condition or {}).get('action') or '').strip().lower()
                if action_name in {'issue', 'approve'}:
                    approval_to_stage_ids.add(transition.to_stage_id)
                elif action_name == 'reject':
                    reject_to_stage_ids.add(transition.to_stage_id)

            # Get all hologram requests
            requests = HologramRequest.objects.select_related(
                'licensee', 'workflow', 'current_stage'
            ).prefetch_related('transactions').all()

            # Deadline time is configurable in DB (public.timer).
            # Store as minutes-from-midnight (recommended): delay_unit=minute, delay_value=1020 for 5:00 PM.
            deadline_timer_code = 'HOLOGRAM_DAILY_ENTRY_DEADLINE_TIME'
            default_deadline_minutes = 17 * 60  # 5:00 PM fallback only
            deadline_minutes = default_deadline_minutes
            try:
                cfg = (
                    SupplyChainTimerConfig.objects.filter(code=deadline_timer_code, is_active=True)
                    .order_by('-updated_at', '-id')
                    .first()
                )
                if cfg:
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

                    if unit == SupplyChainTimerConfig.TIMER_UNIT_MINUTE:
                        deadline_minutes = value
                    elif unit == SupplyChainTimerConfig.TIMER_UNIT_HOUR:
                        deadline_minutes = value * 60
                    elif unit == SupplyChainTimerConfig.TIMER_UNIT_SECOND:
                        deadline_minutes = int(round(value / 60))
                    elif unit == SupplyChainTimerConfig.TIMER_UNIT_DAY:
                        deadline_minutes = value * 24 * 60
                    elif unit == getattr(SupplyChainTimerConfig, 'TIMER_UNIT_MONTH', 'month'):
                        deadline_minutes = value * 30 * 24 * 60
            except Exception:
                deadline_minutes = default_deadline_minutes

            deadline_minutes = int(deadline_minutes or 0) % (24 * 60)
            deadline_time = time(hour=deadline_minutes // 60, minute=deadline_minutes % 60)
            deadline_label = datetime.combine(datetime.today().date(), deadline_time).strftime('%I:%M %p')

            result_data = []
            
            for req in requests:
                
                # Get submission transaction
                submission_txn = req.transactions.filter(
                    stage__is_initial=True
                ).order_by('timestamp').first()
                
                # DB-driven approval transaction: any transition entering a stage via ISSUE/APPROVE action.
                if approval_to_stage_ids:
                    approval_txn = req.transactions.filter(
                        stage_id__in=approval_to_stage_ids
                    ).order_by('timestamp').first()
                else:
                    approval_txn = req.transactions.exclude(stage__is_initial=True).order_by('timestamp').first()
                
                
                # Get daily register entries for this request
                daily_entries = DailyHologramRegister.objects.filter(
                    Q(hologram_request=req) | Q(reference_no=req.ref_no)
                ).select_related('licensee').prefetch_related('rolls_used').order_by('created_at', 'id')
                
                
                # Determine status using stage metadata + transition-derived action mapping.
                status = 'UNDER_PROCESS'
                completed_on_time = None
                is_overdue = False
                time_remaining = None
                deadline = None
                completion_date = None
                completion_time = None
                officer_name = None
                brands_entered = []
                
                if req.current_stage and req.current_stage.is_initial:
                    status = 'APPLIED'
                elif req.current_stage_id and req.current_stage_id in reject_to_stage_ids:
                    status = 'REJECTED'
                elif req.current_stage and req.current_stage.is_final:
                    status = 'COMPLETED'
                
                # Override status if we have daily register entries (means it's completed)
                if daily_entries.exists():
                    status = 'COMPLETED'
                
                # Calculate deadline and SLA if approved
                if approval_txn:
                    # Deadline is configurable time on approval date
                    approval_date = approval_txn.timestamp.date()
                    deadline_naive = datetime.combine(approval_date, deadline_time)
                    deadline = django_timezone.make_aware(deadline_naive) if django_timezone.is_naive(deadline_naive) else deadline_naive
                    
                    now = django_timezone.now()

                    # Completed: decide on-time vs late based on OIC save timestamp (created_at)
                    if status == 'COMPLETED' and daily_entries.exists():
                        last_entry = daily_entries.order_by('-created_at', '-id').first()
                        completion_datetime = last_entry.created_at if last_entry and last_entry.created_at else None
                        
                        if completion_datetime is None and last_entry and last_entry.usage_date:
                            fallback_naive = datetime.combine(last_entry.usage_date, datetime.strptime('00:00', '%H:%M').time())
                            completion_datetime = django_timezone.make_aware(fallback_naive) if django_timezone.is_naive(fallback_naive) else fallback_naive
                        elif completion_datetime is not None and django_timezone.is_naive(completion_datetime):
                            completion_datetime = django_timezone.make_aware(completion_datetime)
                        
                        completion_date = last_entry.usage_date.isoformat() if last_entry and last_entry.usage_date else None
                        completion_time = completion_datetime.strftime('%H:%M:%S') if completion_datetime else None
                        completed_on_time = completion_datetime <= deadline if completion_datetime else None
                        is_overdue = False
                        if completed_on_time is False:
                            time_remaining = f"Completed Late (saved at {completion_time})"
                        elif completed_on_time is True:
                            time_remaining = f"Completed On Time (saved at {completion_time})"
                        
                        # Get officer who entered the data
                        if last_entry and last_entry.licensee:
                            officer_name = last_entry.licensee.manufacturing_unit_name
                        
                        # Get brands entered with allocated/issued/wastage and roll details
                        for entry in daily_entries:
                            rolls_assigned = []
                            for roll in entry.rolls_used.all():
                                rolls_assigned.append({
                                    'rollId': roll.id,
                                    'cartoonNumber': roll.carton_number,
                                    'rollNumber': roll.roll_no,
                                    'quantity': roll.available,
                                    'fromSerial': roll.from_serial,
                                    'toSerial': roll.to_serial,
                                })

                            serial_ranges = []
                            for r in (entry.issued_ranges or []):
                                serial_ranges.append({
                                    'from': r.get('fromSerial') or r.get('from') or r.get('issuedFromSerial') or '',
                                    'to': r.get('toSerial') or r.get('to') or r.get('issuedToSerial') or '',
                                    'count': r.get('quantity') or r.get('count') or 0,
                                    'type': 'ISSUED',
                                })
                            for r in (entry.wastage_ranges or []):
                                serial_ranges.append({
                                    'from': r.get('fromSerial') or r.get('from') or r.get('wastageFromSerial') or '',
                                    'to': r.get('toSerial') or r.get('to') or r.get('wastageToSerial') or '',
                                    'count': r.get('quantity') or r.get('count') or 0,
                                    'type': 'WASTAGE',
                                })

                            if entry.brand_details:
                                brands_entered.append({
                                    'brand': entry.brand_details,
                                    'brandCode': entry.brand_details,
                                    'bottleSize': entry.bottle_size or '',
                                    'allocatedQty': entry.hologram_qty or 0,
                                    'issuedQty': entry.issued_qty or 0,
                                    'wastageQty': entry.wastage_qty or 0,
                                    'damageReason': entry.damage_reason or '',
                                    'rollRange': entry.roll_range or '',
                                    'quantity': entry.issued_qty or 0,  # backward-compatible
                                    'usageDate': entry.usage_date.isoformat(),
                                    'savedAt': entry.created_at.isoformat() if entry.created_at else '',
                                    'rollsAssigned': rolls_assigned,
                                    'serialRanges': serial_ranges,
                                })
                    elif status in {'UNDER_PROCESS', 'APPLIED'}:
                        # OIC has not saved daily entry yet; track remaining time vs configured deadline
                        if now > deadline:
                            is_overdue = True
                            overdue_seconds = int((now - deadline).total_seconds())
                            overdue_hours = overdue_seconds // 3600
                            overdue_minutes = (overdue_seconds % 3600) // 60
                            time_remaining = f"Overdue by {overdue_hours}h {overdue_minutes}m (deadline {deadline_label})"
                        else:
                            remaining_seconds = int((deadline - now).total_seconds())
                            hours_left = remaining_seconds // 3600
                            minutes_left = (remaining_seconds % 3600) // 60
                            time_remaining = f"{hours_left}h {minutes_left}m remaining (deadline {deadline_label})"
                
                
                result_data.append({
                    'id': req.id,
                    'referenceNo': req.ref_no,
                    'distilleryName': req.licensee.manufacturing_unit_name if req.licensee else 'Unknown',
                    'submissionDate': submission_txn.timestamp.isoformat() if submission_txn else req.submission_date.isoformat(),
                    'submissionTime': submission_txn.timestamp.strftime('%H:%M:%S') if submission_txn else '00:00:00',
                    'approvalDate': approval_txn.timestamp.date().isoformat() if approval_txn else None,
                    'approvalTime': approval_txn.timestamp.strftime('%H:%M:%S') if approval_txn else None,
                    'usageDate': req.usage_date.isoformat(),
                    'hologramType': req.hologram_type,
                    'quantity': req.quantity,
                    'status': status,
                    'completedOnTime': completed_on_time,
                    'isOverdue': is_overdue,
                    'timeRemaining': time_remaining,
                    'deadline': deadline.isoformat() if deadline else None,
                    'completionDate': completion_date,
                    'completionTime': completion_time,
                    'officerName': officer_name,
                    'brandsEntered': brands_entered,
                    'currentStage': req.current_stage.name if req.current_stage else 'Unknown'
                })
            
            # Calculate summary statistics
            total_entries = len(result_data)
            applied_count = sum(1 for r in result_data if r['status'] == 'APPLIED')
            under_process_count = sum(1 for r in result_data if r['status'] == 'UNDER_PROCESS')
            completed_on_time_count = sum(1 for r in result_data if r['status'] == 'COMPLETED' and r['completedOnTime'] is True)
            completed_late_count = sum(1 for r in result_data if r['status'] == 'COMPLETED' and r['completedOnTime'] is False)
            overdue_count = sum(1 for r in result_data if r['isOverdue'])
            
            
            return Response({
                'summary': {
                    'totalEntries': total_entries,
                    'applied': applied_count,
                    'underProcess': under_process_count,
                    'completedOnTime': completed_on_time_count,
                    'completedLate': completed_late_count,
                    'overdue': overdue_count
                },
                'entries': result_data
            })
        except Exception as e:
            import traceback
            return Response({
                'error': str(e),
                'summary': {
                    'totalEntries': 0,
                    'applied': 0,
                    'underProcess': 0,
                    'completedOnTime': 0,
                    'completedLate': 0,
                    'overdue': 0
                },
                'entries': []
            }, status=500)


class HologramMonthlyReportViewSet(viewsets.ViewSet):
    """
    ViewSet for generating monthly hologram reports
    Auto-calculates from approved daily register entries
    """
    permission_classes = [permissions.IsAuthenticated]
    
    @action(detail=False, methods=['get'])
    def generate_report(self, request):
        """
        Generate monthly report for a specific month, year, and hologram type
        Query params:
        - month: Month name (e.g., 'January', 'jan')
        - year: Year (e.g., '2026')
        - hologram_type: Type (LOCAL, EXPORT, DEFENCE)
        - licensee_id: Optional licensee ID filter
        - force_refresh: Set to 'true' to bypass cache and get fresh data
        """
        from django.db.models import Sum, Q
        from datetime import datetime
        import calendar
        from django.core.cache import cache
        import logging
        
        logger = logging.getLogger(__name__)
        
        # Get query parameters
        month_param = request.query_params.get('month', '').lower()
        year_param = request.query_params.get('year', str(timezone.now().year))
        hologram_type = request.query_params.get('hologram_type', 'LOCAL').upper()
        licensee_id = request.query_params.get('licensee_id')
        
        # Month mapping
        month_map = {
            'jan': 1, 'january': 1,
            'feb': 2, 'february': 2,
            'mar': 3, 'march': 3,
            'apr': 4, 'april': 4,
            'may': 5,
            'jun': 6, 'june': 6,
            'jul': 7, 'july': 7,
            'aug': 8, 'august': 8,
            'sep': 9, 'september': 9,
            'oct': 10, 'october': 10,
            'nov': 11, 'november': 11,
            'dec': 12, 'december': 12
        }
        
        month_num = month_map.get(month_param, timezone.now().month)
        year_num = int(year_param)
        
        # Get scoped license from user if not provided.
        # Prefer denormalized license_id (NA/NLI format), keep legacy profile-id fallback.
        legacy_profile_id = None
        if hasattr(request.user, 'supply_chain_profile'):
            legacy_profile_id = getattr(request.user.supply_chain_profile, 'id', None)
        scoped_license_id = _resolve_request_license_id(
            profile=getattr(request.user, 'supply_chain_profile', None),
            acting_user=request.user
        )
        if not licensee_id:
            licensee_id = scoped_license_id or (str(legacy_profile_id) if legacy_profile_id else '')
        
        # Build query filters
        filters = Q(
            usage_date__year=year_num,
            usage_date__month=month_num,
            hologram_type=hologram_type,
            approval_status='APPROVED'
        )
        
        if licensee_id:
            normalized_license = str(licensee_id).strip()
            if any(ch.isalpha() for ch in normalized_license) or '/' in normalized_license:
                filters &= (Q(license_id=normalized_license) | Q(licensee__licensee_id=normalized_license))
            else:
                filters &= Q(licensee_id=normalized_license)
        
        # Get approved daily register entries for the month
        daily_entries = DailyHologramRegister.objects.filter(filters).order_by('usage_date', 'id')
        
        # Calculate previous month's closing balance
        prev_month = month_num - 1 if month_num > 1 else 12
        prev_year = year_num if month_num > 1 else year_num - 1
        
        # Get previous month's data
        prev_filters = Q(
            usage_date__year=prev_year,
            usage_date__month=prev_month,
            hologram_type=hologram_type,
            approval_status='APPROVED'
        )
        if licensee_id:
            normalized_license = str(licensee_id).strip()
            if any(ch.isalpha() for ch in normalized_license) or '/' in normalized_license:
                prev_filters &= (Q(license_id=normalized_license) | Q(licensee__licensee_id=normalized_license))
            else:
                prev_filters &= Q(licensee_id=normalized_license)
        
        prev_entries = DailyHologramRegister.objects.filter(prev_filters)
        
        # Calculate previous month totals
        prev_utilized = prev_entries.aggregate(total=Sum('issued_qty'))['total'] or 0
        prev_wastage = prev_entries.aggregate(total=Sum('wastage_qty'))['total'] or 0
        
        # Get fresh arrivals for current month (from HologramRollsDetails)
        arrival_filters = Q(
            received_date__year=year_num,
            received_date__month=month_num,
            type=hologram_type
        )
        if licensee_id:
            normalized_license = str(licensee_id).strip()
            if any(ch.isalpha() for ch in normalized_license) or '/' in normalized_license:
                arrival_filters &= (Q(license_id=normalized_license) | Q(procurement__licensee__licensee_id=normalized_license))
            else:
                arrival_filters &= Q(procurement__licensee_id=normalized_license)
        
        arrivals = HologramRollsDetails.objects.filter(arrival_filters)
        fresh_arrivals = arrivals.aggregate(total=Sum('total_count'))['total'] or 0
        arrival_count = arrivals.count()
        
        # Calculate current month totals
        total_utilized = daily_entries.aggregate(total=Sum('issued_qty'))['total'] or 0
        total_wastage = daily_entries.aggregate(total=Sum('wastage_qty'))['total'] or 0
        utilization_count = daily_entries.filter(issued_qty__gt=0).count()
        wastage_count = daily_entries.filter(wastage_qty__gt=0).count()
        
        # Get opening stock (previous month's closing balance)
        # This should come from the previous month's report or initial procurement
        opening_stock = 0
        
        # Try to get from previous month's closing
        if prev_month and prev_year:
            # Get all rolls up to previous month
            all_prev_rolls = HologramRollsDetails.objects.filter(
                Q(received_date__year__lt=prev_year) |
                Q(received_date__year=prev_year, received_date__month__lte=prev_month),
                type=hologram_type
            )
            if licensee_id:
                normalized_license = str(licensee_id).strip()
                if any(ch.isalpha() for ch in normalized_license) or '/' in normalized_license:
                    all_prev_rolls = all_prev_rolls.filter(
                        Q(license_id=normalized_license) | Q(procurement__licensee__licensee_id=normalized_license)
                    )
                else:
                    all_prev_rolls = all_prev_rolls.filter(procurement__licensee_id=normalized_license)
            
            total_received = all_prev_rolls.aggregate(total=Sum('total_count'))['total'] or 0
            
            # Get all usage up to previous month
            all_prev_usage = DailyHologramRegister.objects.filter(
                Q(usage_date__year__lt=prev_year) |
                Q(usage_date__year=prev_year, usage_date__month__lte=prev_month),
                hologram_type=hologram_type,
                approval_status='APPROVED'
            )
            if licensee_id:
                normalized_license = str(licensee_id).strip()
                if any(ch.isalpha() for ch in normalized_license) or '/' in normalized_license:
                    all_prev_usage = all_prev_usage.filter(
                        Q(license_id=normalized_license) | Q(licensee__licensee_id=normalized_license)
                    )
                else:
                    all_prev_usage = all_prev_usage.filter(licensee_id=normalized_license)
            
            total_prev_utilized = all_prev_usage.aggregate(total=Sum('issued_qty'))['total'] or 0
            total_prev_wastage = all_prev_usage.aggregate(total=Sum('wastage_qty'))['total'] or 0
            
            opening_stock = total_received - total_prev_utilized - total_prev_wastage
        
        # Calculate closing balance
        closing_balance = opening_stock + fresh_arrivals - total_utilized - total_wastage
        
        # Build statement rows
        statement_rows = []
        
        # Group entries by date
        from collections import defaultdict
        entries_by_date = defaultdict(list)
        for entry in daily_entries:
            entries_by_date[entry.usage_date].append(entry)
        
        # Add arrival rows
        for arrival in arrivals:
            statement_rows.append({
                'rowType': 'ARRIVAL',
                'label': f"Arrival - {arrival.received_date.strftime('%d %b %Y')}",
                'freshArrival': arrival.total_count,
                'closingBalance': None,  # Will be calculated on frontend
                'meta': {
                    'cartoonNumber': arrival.carton_number,
                    'notes': f"Received {arrival.total_count} holograms"
                }
            })
        
        # Add utilization/wastage rows
        for date, entries in sorted(entries_by_date.items()):
            for entry in entries:
                row = {
                    'rowType': 'UTILIZATION',
                    'label': f"Utilization - {date.strftime('%d %b %Y')}",
                    'brandDetails': entry.brand_details or '-',
                    'bottleSize': entry.bottle_size or '-',
                    'utilizationFrom': entry.issued_from or '-',
                    'utilizationTo': entry.issued_to or '-',
                    'utilizationQty': entry.issued_qty,
                    'wastageFrom': entry.wastage_from or '-',
                    'wastageTo': entry.wastage_to or '-',
                    'wastageQty': entry.wastage_qty,
                    'leftOver': 0,  # Calculated on frontend
                    'closingBalance': None,  # Calculated on frontend
                    'meta': {
                        'referenceNo': entry.reference_no,
                        'cartoonNumber': entry.cartoon_number,
                        'serialRange': f"{entry.issued_from}-{entry.issued_to}" if entry.issued_from and entry.issued_to else None
                    }
                }
                
                # Add utilization details if multiple ranges
                if entry.issued_ranges:
                    row['utilizationDetails'] = [{
                        'rollName': entry.cartoon_number,
                        'ranges': [
                            {
                                'from': r.get('fromSerial'),
                                'to': r.get('toSerial'),
                                'qty': r.get('quantity')
                            }
                            for r in entry.issued_ranges
                        ]
                    }]
                
                # Add wastage details if multiple ranges
                if entry.wastage_ranges:
                    row['wastageDetails'] = [{
                        'rollName': entry.cartoon_number,
                        'ranges': [
                            {
                                'from': r.get('fromSerial'),
                                'to': r.get('toSerial'),
                                'qty': r.get('quantity')
                            }
                            for r in entry.wastage_ranges
                        ]
                    }]
                
                statement_rows.append(row)
        
        # Build response
        response_data = {
            'month': month_param,
            'year': year_param,
            'hologramType': hologram_type,
            'overviewSummary': {
                'openingStock': opening_stock,
                'totalArrivals': fresh_arrivals,
                'arrivalCount': arrival_count,
                'totalUtilized': total_utilized,
                'utilizationCount': utilization_count,
                'totalWastage': total_wastage,
                'wastageCount': wastage_count,
                'closingBalance': closing_balance
            },
            'statementRows': statement_rows,
            'approvedEntriesCount': daily_entries.count(),
            'previousMonthBalance': opening_stock
        }
        
        return Response(response_data)
