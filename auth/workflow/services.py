from django.db import transaction
from django.core.exceptions import ValidationError, PermissionDenied
from django.contrib.contenttypes.models import ContentType
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
            raise ValidationError("Application is not in initial stage.")

        # Find who should receive it
        perm = StagePermission.objects.filter(stage=initial_stage, can_process=True).first()
        if not perm:
            raise ValidationError("No role assigned to initial stage.")

        # Log transaction
        Transaction.objects.create(
            content_type=ContentType.objects.get_for_model(application),
            object_id=str(application.pk),
            performed_by=user,
            forwarded_by=user,
            forwarded_to=perm.role,
            stage=initial_stage,
            remarks=remarks or "Application submitted"
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
            raise ValidationError(f"Invalid transition {application.current_stage.name} to {to_stage.name}")

        for key, val in (transition.condition or {}).items():
            if (context or {}).get(key) != val:
                raise ValidationError(f"Condition failed: {key}={val}")

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
    def resolve_objections(application, user):
        if user.role.name != "licensee":
            raise PermissionDenied("Only licensee can resolve objections.")
        if application.objections.filter(is_resolved=False).exists():
            raise ValidationError("Unresolved objections remain.")

        # Return to the *original* review stage (you can store it or infer)
        original_stage = application.transactions.exclude(
            stage__name__contains="objection"
        ).order_by('-id').first().stage

        application.current_stage = original_stage
        application.save(update_fields=['current_stage'])

        Transaction.objects.create(
            content_type=ContentType.objects.get_for_model(application),
            object_id=str(application.pk),
            performed_by=user,
            forwarded_by=user,
            forwarded_to=StagePermission.objects.filter(stage=original_stage, can_process=True).first().role,
            stage=original_stage,
            remarks="Objections resolved"
        )