from datetime import timezone
from django.db import transaction
from django.core.exceptions import ValidationError, PermissionDenied
from django.contrib.contenttypes.models import ContentType

from django.apps import apps
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
    def validate_transition(application, to_stage, context=None):
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
            for key, expected in transition.condition.items():
                actual = (context or {}).get(key)
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
        WorkflowService.validate_transition(application, target_stage, context)

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
                resolved_on=timezone.now(),
                resolved_by=user
            )

        # Find the stage we came from (before entering objection)
        original_stage = application.transactions.filter(
            stage__name__contains='_objection'
        ).exclude(stage=application.current_stage).order_by('-id').first()

        if not original_stage:
            # Fallback: last non-objection stage
            original_stage = application.transactions.exclude(stage__name__contains='_objection').order_by('-id').first()

        if not original_stage:
            raise ValidationError("Cannot determine original stage")

        application.current_stage = original_stage.stage
        application.save(update_fields=['current_stage'])

        # Log the return
        Transaction.objects.create(
            content_type=ContentType.objects.get_for_model(application),
            object_id=str(application.pk),
            performed_by=user,
            forwarded_by=user,
            forwarded_to=StagePermission.objects.filter(stage=original_stage.stage, can_process=True).first().role,
            stage=original_stage.stage,
            remarks="Objections resolved and application returned to previous stage"
        )