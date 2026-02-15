from django.utils import timezone
from django.db import transaction
from django.core.exceptions import ValidationError, PermissionDenied
from django.contrib.contenttypes.models import ContentType

from django.apps import apps
from .models import (
    WorkflowTransition, StagePermission,
    Transaction, Objection
)

# UI Configuration for Workflow Actions (Moved from Frontend)
ACTION_CONFIGS = {
    'APPROVE': {
        'label': 'Approve',
        'icon': 'check_circle',
        'color': 'primary',
        'tooltip': 'Approve Application',
        'requires_confirmation': True,
        'confirmation_message': 'Are you sure you want to approve this application?'
    },
    'REJECT': {
        'label': 'Reject',
        'icon': 'cancel',
        'color': 'warn',
        'tooltip': 'Reject Application',
        'requires_confirmation': True,
        'confirmation_message': 'Are you sure you want to reject this application?'
    },
    'FORWARD': {
        'label': 'Forward',
        'icon': 'forward',
        'color': 'primary',
        'tooltip': 'Forward to Next Stage',
        'requires_confirmation': True,
        'confirmation_message': 'Are you sure you want to forward this application?'
    },
    'RETURN': {
        'label': 'Return',
        'icon': 'undo',
        'color': 'warning',
        'tooltip': 'Return to Previous Stage',
        'requires_confirmation': True,
        'confirmation_message': 'Are you sure you want to return this application?'
    },
    'VERIFY': {
        'label': 'Verify',
        'icon': 'verified',
        'color': 'primary',
        'tooltip': 'Verify Application',
        'requires_confirmation': True,
        'confirmation_message': 'Are you sure you want to verify this application?'
    },
    'ISSUE': {
        'label': 'Issue',
        'icon': 'assignment_turned_in',
        'color': 'success',
        'tooltip': 'Issue Permit/Certificate',
        'requires_confirmation': True,
        'confirmation_message': 'Are you sure you want to issue this permit?'
    },
    'PAY': {
        'label': 'Submit Payment',
        'icon': 'payment',
        'color': 'primary',
        'tooltip': 'Submit Payment',
        'requires_confirmation': True,
        'confirmation_message': 'Are you sure you want to submit payment?'
    },
    'TERMINATE': {
        'label': 'Terminate',
        'icon': 'block',
        'color': 'danger',
        'tooltip': 'Terminate Application',
        'requires_confirmation': True,
        'confirmation_message': 'Are you sure you want to terminate this application?'
    },
    'VIEW': {
        'label': 'View',
        'icon': 'visibility',
        'color': 'primary',
        'tooltip': 'View Details'
    },
    'REQUEST_CANCELLATION': {
        'label': 'Request Cancellation',
        'icon': 'cancel',
        'color': 'warn',
        'tooltip': 'Request Cancellation of Approved Application',
        'requires_confirmation': True,
        'confirmation_message': 'Are you sure you want to request cancellation of this approved application?'
    },
    'REQUEST_REVALIDATION': {
        'label': 'Request Revalidation',
        'icon': 'restore',
        'color': 'warn',
        'tooltip': 'Request Revalidation',
        'requires_confirmation': True,
        'confirmation_message': 'The permit validity has been extended. Do you want to proceed with revalidation?'
    },
    'SUBMITPAYSLIP': {
        'label': 'Submit Pay Slip',
        'icon': 'receipt_long',
        'color': 'primary',
        'tooltip': 'Submit Payment Slip',
        'requires_confirmation': True,
        'confirmation_message': 'Are you sure you want to submit the pay slip?'
    },
    'APPROVEPAYSLIP': {
        'label': 'Approve Pay Slip',
        'icon': 'check_circle',
        'color': 'accent',
        'tooltip': 'Approve Payment Slip',
        'requires_confirmation': True,
        'confirmation_message': 'Are you sure you want to approve the pay slip?'
    },
    'REJECTPAYSLIP': {
        'label': 'Reject Pay Slip',
        'icon': 'cancel',
        'color': 'warn',
        'tooltip': 'Reject Payment Slip',
        'requires_confirmation': True,
        'confirmation_message': 'Are you sure you want to reject the pay slip?'
    },
    # Default fallback
    'DEFAULT': {
        'label': 'Action',
        'icon': 'touch_app',
        'color': 'primary',
        'tooltip': 'Perform Action',
        'requires_confirmation': True,
        'confirmation_message': 'Are you sure?'
    }
}

# Mapping: (app_label, model_name) -> Serializer class
SERIALIZER_MAPPING = {
    # (app_label, model_name_lower): 'full.import.path.to.Serializer'
    ('license_application', 'licenseapplication'): 'models.transactional.license_application.serializers.LicenseApplicationSerializer',
    ('new_license_application', 'newlicenseapplication'): 'models.transactional.new_license_application.serializers.NewLicenseApplicationSerializer',
    ('salesman_barman', 'salesmanbarmanmodel'): 'models.transactional.salesman_barman.serializers.SalesmanBarmanSerializer',
    ('company_registration', 'companymodel'): 'models.transactional.company_registration.serializers.CompanySerializer',
    ('ena_requisition_details', 'enarequisitiondetail'): 'models.transactional.supply_chain.ena_requisition_details.serializers.EnaRequisitionDetailSerializer',
    ('ena_revalidation_details', 'enarevalidationdetail'): 'models.transactional.supply_chain.ena_revalidation_details.serializers.EnaRevalidationDetailSerializer',
    ('ena_cancellation_details', 'enacancellationdetail'): 'models.transactional.supply_chain.ena_cancellation_details.serializers.EnaCancellationDetailSerializer',
}

class WorkflowService:

    @staticmethod
    def _normalize_token(value):
        return ''.join(ch for ch in str(value or '').lower() if ch.isalnum())

    @staticmethod
    def _condition_role_matches(condition, user):
        condition = condition or {}
        role = getattr(user, 'role', None)
        user_role_id = getattr(role, 'id', None)

        cond_role_id = condition.get('role_id')
        if cond_role_id is not None:
            if user_role_id is None:
                return False
            try:
                return int(cond_role_id) == int(user_role_id)
            except (TypeError, ValueError):
                return False

        cond_role = WorkflowService._normalize_token(condition.get('role'))
        if not cond_role:
            return True

        user_role_name = WorkflowService._normalize_token(getattr(role, 'name', ''))
        return cond_role == user_role_name

    @staticmethod
    def _transition_matches_submit(transition, user):
        condition = transition.condition or {}
        if not WorkflowService._condition_role_matches(condition, user):
            return False

        cond_action = str(condition.get('action') or '').strip().lower()
        if cond_action and cond_action not in {'submit', 'submitted', 'create', 'apply'}:
            return False
        return True

    @staticmethod
    def _transition_priority_for_submit(transition, user):
        """
        Lower tuple wins.
        Preference order:
        1) matching submit-condition transition
        2) transition whose target stage has processor role mapped
        3) target processor role is non-licensee
        4) lower role_precedence (earlier processing role)
        5) lower transition id for deterministic tie-break
        """
        condition = transition.condition or {}
        cond_action = str(condition.get('action') or '').strip().lower()
        action_rank = 1
        if WorkflowService._transition_matches_submit(transition, user):
            action_rank = 0
        elif cond_action:
            action_rank = 2

        perm = StagePermission.objects.filter(
            stage=transition.to_stage,
            can_process=True
        ).select_related('role').first()
        has_perm_rank = 0 if (perm and perm.role) else 1

        role_token = WorkflowService._normalize_token(getattr(getattr(perm, 'role', None), 'name', ''))
        non_licensee_rank = 0 if role_token not in {'licensee', 'licenseuser', 'licenseeuser'} else 1
        precedence_rank = getattr(getattr(perm, 'role', None), 'role_precedence', 999) if perm else 999
        id_rank = getattr(transition, 'id', 0) or 0

        return (action_rank, has_perm_rank, non_licensee_rank, precedence_rank, id_rank)

    @staticmethod
    def get_action_config(action_name):
        """
        Returns the UI configuration (label, icon, color, etc.) for a given action name.
        """
        if not action_name:
            return ACTION_CONFIGS['DEFAULT']
        
        config = ACTION_CONFIGS.get(action_name.upper())
        if not config:
            # Create a default config for unknown actions
            config = {
                **ACTION_CONFIGS['DEFAULT'],
                'label': action_name.replace('_', ' ').title(),
            }
        
        # Ensure 'action' key is always present in the returned object
        return {**config, 'action': action_name}

    @staticmethod
    @transaction.atomic
    def submit_application(application, user, remarks=None):
        initial_stage = application.current_stage
        if not initial_stage.is_initial:
            raise ValidationError("Not in initial stage")

        # 1. Log submission
        Transaction.objects.create(
            content_type=ContentType.objects.get_for_model(application),
            object_id=str(application.pk),
            performed_by=user,
            forwarded_by=getattr(user, "role", None),
            forwarded_to=None,
            stage=initial_stage,
            remarks=remarks or "Application submitted by applicant"
        )

        # 2. Auto-advance using DB transitions (optionally constrained by role/action)
        transitions = list(WorkflowTransition.objects.filter(
            workflow=application.workflow,
            from_stage=initial_stage
        ).select_related('to_stage'))
        if not transitions:
            raise ValidationError(f"No transition configured from stage '{initial_stage.name}'")

        transition = min(
            transitions,
            key=lambda t: WorkflowService._transition_priority_for_submit(t, user)
        )
        if WorkflowService._transition_priority_for_submit(transition, user)[0] == 2:
            role_name = getattr(getattr(user, 'role', None), 'name', None)
            raise ValidationError(
                f"No submission transition from stage '{initial_stage.name}' for role '{role_name}'."
            )

        application.current_stage = transition.to_stage
        application.save(update_fields=['current_stage'])

        # 3. Enforce that next stage has an assigned processing role
        perm = StagePermission.objects.filter(stage=transition.to_stage, can_process=True).first()
        if not perm or not perm.role:
            raise ValidationError(
                f"No role assigned to process stage '{transition.to_stage.name}'."
            )

        # 4. Log auto-forward
        Transaction.objects.create(
            content_type=ContentType.objects.get_for_model(application),
            object_id=str(application.pk),
            performed_by=user,
            forwarded_by=perm.role,
            forwarded_to=perm.role,
            stage=transition.to_stage,
            remarks="Application forwarded to Level 1 for review"
        )
        
    @staticmethod
    def get_next_stages(application):
        return WorkflowTransition.objects.filter(
            workflow=application.workflow,
            from_stage=application.current_stage
        ).select_related('to_stage')

    @staticmethod
    def validate_transition(application, to_stage, context=None, user=None):
        transition = WorkflowTransition.objects.filter(
            workflow=application.workflow,
            from_stage=application.current_stage,
            to_stage=to_stage
        ).first()

        if not transition:
            raise ValidationError(
                f"Invalid transition from {application.current_stage.name} "
                f"to {to_stage.name} in workflow {application.workflow.name}"
            )

        if transition.condition:
            context = context or {}
            for key, expected in transition.condition.items():
                # role / role_id are validated against authenticated user's role
                if key in {"role", "role_id"}:
                    if user is None:
                        raise ValidationError(f"Condition failed: {key} cannot be validated without user")
                    if not WorkflowService._condition_role_matches({key: expected}, user):
                        raise ValidationError(f"Condition failed: {key} must be {expected}")
                    continue

                # action may be omitted by callers that only send target stage.
                # in that case, do not fail; transition target itself is already explicit.
                if key == "action":
                    actual_action = context.get("action")
                    if actual_action is None:
                        continue
                    if str(actual_action).strip().lower() != str(expected).strip().lower():
                        raise ValidationError(f"Condition failed: {key} must be {expected}")
                    continue

                actual = context.get(key)
                if actual != expected:
                    raise ValidationError(f"Condition failed: {key} must be {expected}")

        return transition

    @staticmethod
    @transaction.atomic
    def advance_stage(application, user, target_stage, context=None, remarks=None):
        context = context or {}

        # ---------- Permission ----------
        if not user.is_superuser:
            if not StagePermission.objects.filter(
                stage=application.current_stage,
                role=user.role,
                can_process=True
            ).exists():
                raise PermissionDenied("You cannot process this stage.")

        # ---------- Transition ----------
        WorkflowService.validate_transition(application, target_stage, context, user=user)

        # ---------- App-specific hooks (via context) ----------
        # if getattr(application, 'is_fee_calculated', None) is not None and target_stage.name == "level_1":
        #     if context.get("action") == "set_fee":
        #         if application.is_fee_calculated:
        #             raise ValidationError("Fee already set.")
        #         fee = context.get("fee_amount")
        #         if not fee:
        #             raise ValidationError("fee_amount required.")
        #         application.yearly_license_fee = str(float(fee))
        #         application.is_fee_calculated = True

        # ---------- Update stage ----------
        application.current_stage = target_stage
        application.save(update_fields=['current_stage'])

        # ---------- Forwarded role ----------
        forwarded_to = None
        if "objection" in target_stage.name.lower() or target_stage.name == "awaiting_payment":
            first_txn = application.transactions.order_by('id').first()
            if first_txn and first_txn.performed_by.role:
                forwarded_to = first_txn.performed_by.role
        else:
            perm = StagePermission.objects.filter(stage=target_stage, can_process=True).first()
            if perm:
                forwarded_to = perm.role

        # ---------- Log ----------
        Transaction.objects.create(
            content_type=ContentType.objects.get_for_model(application),
            object_id=str(application.pk),
            performed_by=user,
            forwarded_by=getattr(user, "role", None),
            forwarded_to=forwarded_to,
            stage=target_stage,
            remarks=remarks or context.get("remarks", "")
        )

    @staticmethod
    def get_application_by_id(application_id):
        from django.db import models
        from auth.workflow.models import WorkflowStage

        # Find all models that have a ForeignKey to WorkflowStage named 'current_stage'
        for model in apps.get_models():
            if hasattr(model, 'current_stage') and isinstance(getattr(model, 'current_stage'), models.ForeignKey):
                field = model.current_stage.field
                if field.related_model == WorkflowStage:
                    try:
                        return model.objects.select_related('current_stage', 'workflow').get(
                            application_id=application_id
                        )
                    except model.DoesNotExist:
                        continue
        return None

    @staticmethod
    @transaction.atomic
    def raise_objection(application, user, target_stage, objections, remarks=None):
        if not objections:
            raise ValidationError("Objections list cannot be empty.")
        WorkflowService.validate_transition(application, target_stage, {"has_objections": True})

        for obj in objections:
            Objection.objects.create(
                content_type=ContentType.objects.get_for_model(application),
                object_id=str(application.pk),
                field_name=obj["field"],
                remarks=obj["remarks"],
                raised_by=user,
                stage=target_stage
            )

        application.current_stage = target_stage
        application.save(update_fields=['current_stage'])

        first_txn = application.transactions.order_by('id').first()
        applicant_role = first_txn.performed_by.role if first_txn else None

        Transaction.objects.create(
            content_type=ContentType.objects.get_for_model(application),
            object_id=str(application.pk),
            performed_by=user,
            forwarded_by=getattr(user, "role", None),
            forwarded_to=applicant_role,
            stage=target_stage,
            remarks=remarks or "Objection raised"
        )

    @staticmethod
    @transaction.atomic
    def resolve_objections(application, user, objection_ids=None, updated_fields=None, remarks=None):

        if user.role.name != "licensee":
            raise PermissionDenied("Only licensee can resolve objections.")

        updated_fields = updated_fields or {}
        remarks = remarks or "Objections resolved and application returned to previous stage"

        # --- 1. Early exit if no unresolved objections ---
        unresolved_qs = application.objections.filter(is_resolved=False)
        if objection_ids:
            unresolved_qs = unresolved_qs.filter(id__in=objection_ids)

        if not unresolved_qs.exists():
            raise ValidationError("No unresolved objections found. Nothing to resolve.")

        # --- 2. Strict validation: all objected fields must be updated ---
        required_fields = {obj.field_name for obj in unresolved_qs}
        updated_keys = set(updated_fields.keys())
        missing = required_fields - updated_keys
        if missing:
            raise ValidationError(
                f"Please provide updates for the following objected fields: {', '.join(missing)}"
            )

        # --- 3. Apply field updates using the correct app-specific serializer ---
        if updated_fields:
            app_label = application._meta.app_label
            model_name = application._meta.model_name.lower()

            key = (app_label, model_name)
            serializer_path = SERIALIZER_MAPPING.get(key)

            if not serializer_path:
                raise ValidationError(f"No serializer configured for {app_label}.{model_name}")

            try:
                module_path, serializer_name = serializer_path.rsplit('.', 1)
                module = __import__(module_path, fromlist=[serializer_name])
                AppSerializer = getattr(module, serializer_name)
            except Exception as e:
                raise ValidationError(f"Failed to load serializer: {str(e)}")

            serializer = AppSerializer(application, data=updated_fields, partial=True)
            serializer.is_valid(raise_exception=True)
            serializer.save()

        # --- 4. Mark objections as resolved ---
        qs = application.objections.filter(is_resolved=False)
        if objection_ids:
            qs = qs.filter(id__in=objection_ids)
        qs.update(is_resolved=True, resolved_on=timezone.now())

        # --- 5. Find the transaction that moved INTO the current objection stage ---
        entry_to_objection_txn = application.transactions.filter(
            stage=application.current_stage
        ).order_by('-timestamp').first()

        if not entry_to_objection_txn:
            raise ValidationError("Cannot find the transaction that entered the objection stage")

        # The officer who raised the objection (performed_by in the entry txn)
        forward_to = (
            entry_to_objection_txn.performed_by.role
            if entry_to_objection_txn.performed_by and entry_to_objection_txn.performed_by.role
            else None
        )

        # --- 6. Determine the original non-objection stage to return to ---
        recent_txns = application.transactions.order_by('-timestamp')[:2]
        if len(recent_txns) < 2:
            raise ValidationError("Insufficient transaction history")
        original_txn = recent_txns[1]
        if not original_txn:
            original_txn = application.transactions.exclude(
                stage__name__contains='_objection'
            ).order_by('-id').first()

        if not original_txn:
            raise ValidationError("Cannot determine original stage")

        application.current_stage = original_txn.stage
        application.save(update_fields=['current_stage'])

        # --- 7. Log the return: forward back to the officer ---
        Transaction.objects.create(
            content_type=ContentType.objects.get_for_model(application),
            object_id=str(application.pk),
            performed_by=user,
            forwarded_by=getattr(user, "role", None),
            forwarded_to=forward_to,
            stage=original_txn.stage,
            remarks=remarks
        )
