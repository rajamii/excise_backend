from django.db import transaction
from django.core.exceptions import ValidationError, PermissionDenied
from django.contrib.contenttypes.models import ContentType
from django.apps import apps
from django.utils import timezone
from .models import (
    WorkflowTransition, StagePermission,
    Transaction, Objection
)


class WorkflowService:

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
            forwarded_by=user,
            forwarded_to=None,
            stage=initial_stage,
            remarks=remarks or "Application submitted by applicant"
        )

        # 2. Auto-advance to level_1
        transition = WorkflowTransition.objects.filter(
            workflow=application.workflow,
            from_stage=initial_stage
        ).first()
        if not transition:
            raise ValidationError("No transition from applicant_applied")

        application.current_stage = transition.to_stage
        application.save(update_fields=['current_stage'])

        # 3. Log auto-forward
        perm = StagePermission.objects.filter(stage=transition.to_stage, can_process=True).first()
        Transaction.objects.create(
            content_type=ContentType.objects.get_for_model(application),
            object_id=str(application.pk),
            performed_by=user,
            forwarded_by=user,
            forwarded_to=perm.role if perm else None,
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
    def validate_transition(application, to_stage, context=None):
        """
        IMPROVED: Validates transition with proper context matching.
        Now checks if context contains required keys, not exact match.
        """
        context = context or {}
        
        # Find all transitions from current stage to target stage
        transitions = WorkflowTransition.objects.filter(
            workflow=application.workflow,
            from_stage=application.current_stage,
            to_stage=to_stage
        )

        if not transitions.exists():
            raise ValidationError(
                f"Invalid transition from {application.current_stage.name} "
                f"to {to_stage.name} in workflow {application.workflow.name}"
            )

        # Try to find a matching transition based on conditions
        for transition in transitions:
            if not transition.condition:
                # Empty condition = always valid
                return transition
            
            # Check if ALL required keys in condition are satisfied by context
            condition_match = True
            for key, expected_value in transition.condition.items():
                actual_value = context.get(key)
                if actual_value != expected_value:
                    condition_match = False
                    break
            
            if condition_match:
                return transition
        
        # If we get here, no transition matched
        raise ValidationError(
            f"Invalid transition from {application.current_stage.name} to {to_stage.name}. "
            f"Required conditions not met. Context: {context}, "
            f"Available transitions require: {[t.condition for t in transitions]}"
        )

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

        # ---------- Transition Validation ----------
        WorkflowService.validate_transition(application, target_stage, context)

        # ---------- Update stage ----------
        application.current_stage = target_stage
        application.save(update_fields=['current_stage'])

        # ---------- Determine forwarded role ----------
        forwarded_to = None
        if "objection" in target_stage.name.lower() or target_stage.name == "awaiting_payment":
            # Send back to licensee
            first_txn = application.transactions.order_by('id').first()
            if first_txn and first_txn.performed_by and first_txn.performed_by.role:
                forwarded_to = first_txn.performed_by.role
        else:
            # Send to role that can process this stage
            perm = StagePermission.objects.filter(stage=target_stage, can_process=True).first()
            if perm:
                forwarded_to = perm.role

        # ---------- Log Transaction ----------
        Transaction.objects.create(
            content_type=ContentType.objects.get_for_model(application),
            object_id=str(application.pk),
            performed_by=user,
            forwarded_by=user,
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
            if hasattr(model, 'current_stage'):
                field = getattr(model, 'current_stage')
                if hasattr(field, 'field') and isinstance(field.field, models.ForeignKey):
                    if field.field.related_model == WorkflowStage:
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
        applicant_role = first_txn.performed_by.role if first_txn and first_txn.performed_by else None

        Transaction.objects.create(
            content_type=ContentType.objects.get_for_model(application),
            object_id=str(application.pk),
            performed_by=user,
            forwarded_by=user,
            forwarded_to=applicant_role,
            stage=target_stage,
            remarks=remarks or "Objection raised"
        )

    @staticmethod
    @transaction.atomic
    def resolve_objections(application, user, objection_ids=None):
        if user.role.name != "licensee":
            raise PermissionDenied("Only licensee can resolve objections.")

        # Mark specific or all objections as resolved
        objections_qs = application.objections.filter(is_resolved=False)
        if objection_ids:
            objections_qs = objections_qs.filter(id__in=objection_ids)

        if objections_qs.exists():
            objections_qs.update(
                is_resolved=True,
                resolved_on=timezone.now()
            )

        # Find the stage we came from (before entering objection)
        original_stage = application.transactions.filter(
            stage__name__contains='_objection'
        ).exclude(stage=application.current_stage).order_by('-id').first()

        if not original_stage:
            # Fallback: last non-objection stage
            original_stage = application.transactions.exclude(
                stage__name__contains='_objection'
            ).order_by('-id').first()

        if not original_stage:
            raise ValidationError("Cannot determine original stage")

        application.current_stage = original_stage.stage
        application.save(update_fields=['current_stage'])

        # Log the return
        perm = StagePermission.objects.filter(
            stage=original_stage.stage, 
            can_process=True
        ).first()
        
        Transaction.objects.create(
            content_type=ContentType.objects.get_for_model(application),
            object_id=str(application.pk),
            performed_by=user,
            forwarded_by=user,
            forwarded_to=perm.role if perm else None,
            stage=original_stage.stage,
            remarks="Objections resolved and application returned to previous stage"
        )