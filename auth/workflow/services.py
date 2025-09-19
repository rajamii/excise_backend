from django.core.exceptions import ValidationError, PermissionDenied
from django.db import transaction
from .permissions import StagePermission
from .models import WorkflowTransition, StagePermission
from models.transactional.license_application.models import LicenseApplicationTransaction, SiteEnquiryReport, Objection
from models.masters.core.models import LicenseCategory
from models.masters.license.models import License
from django.utils import timezone

class WorkflowService:
    @staticmethod
    def get_next_stages(workflow, current_stage):
        return WorkflowTransition.objects.filter(
            workflow=workflow,
            from_stage=current_stage
        ).select_related("to_stage")

    @staticmethod
    def validate_transition(workflow, from_stage, to_stage, context=None):

        transition = WorkflowTransition.objects.filter(
            workflow=workflow,
            from_stage=from_stage,
            to_stage=to_stage
        ).first()

        if not transition:
            raise ValidationError(f"Invalid transition: {from_stage.name} → {to_stage.name}")
        
        condition = transition.condition or {}
        for key, expected_value in condition.items():
            if (context or {}).get(key) != expected_value:
                raise ValidationError(f"Condition not met: {key}={expected_value}")

    @staticmethod
    @transaction.atomic
    def advance_stage(application, user, target_stage, context_data=None, skip_permission_check=False):

        context_data = context_data or {}

        # Check permissions
        if not skip_permission_check and not user.is_superuser:
            if not StagePermission.objects.filter(
                stage=application.current_stage,
                role=user.role,
                can_process=True
            ).exists():
                raise PermissionError(f"Role {user.role.name} cannot process stage {target_stage.name}")

        # Validate transition
        WorkflowService.validate_transition(
            workflow=application.workflow,
            from_stage=application.current_stage,
            to_stage=target_stage,
            context=context_data,
        )

        # Special logic for specific stages
        if target_stage.name == "level_1":
            if context_data.get("action") == "set_fee":
                if application.is_fee_calculated:
                    raise ValidationError("Fee already calculated.")
                fee_amount = context_data.get("fee_amount")
                if not fee_amount:
                    raise ValidationError("Fee amount must be provided.")
                try:
                    application.yearly_license_fee = str(float(fee_amount))
                    application.is_fee_calculated = True
                except ValueError:
                    raise ValidationError("Invalid fee amount format.")

        elif target_stage.name == "level_2":
            if context_data.get("action") == "update_category":
                new_category_id = context_data.get("new_license_category")
                if new_category_id:
                    try:
                        new_category = LicenseCategory.objects.get(pk=new_category_id)
                        application.license_category = new_category
                        application.is_license_category_updated = True
                    except LicenseCategory.DoesNotExist:
                        raise ValidationError("Invalid license category ID.")

        elif target_stage.name == "awaiting_payment":
            if not SiteEnquiryReport.objects.filter(application=application).exists():
                raise ValidationError("Site Enquiry Report must be filled.")

        elif target_stage.name == "approved":
            application.is_approved = True
            license = License.objects.create(
                application=application,
                license_type=application.license_type,
                establishment_name=application.establishment_name,
                licensee_name=application.member_name,
                excise_district=application.excise_district,
                issue_date=timezone.now().date(),
                valid_up_to=application.valid_up_to or (timezone.now().date() + timezone.timedelta(days=365)),
            )
            application.license_no = license.license_id

        # Update stage
        application.current_stage = target_stage
        application.save()
        
        
        # Determine forwarded_to_role
        forwarded_to_role = None
        stage_perms = StagePermission.objects.filter(stage=target_stage, can_process=True)
        if target_stage.name in ["applicant_applied", "awaiting_payment", "level_1_objection", "level_2_objection", 
                                "level_3_objection", "level_4_objection", "level_5_objection"]:
            first_txn = LicenseApplicationTransaction.objects.filter(
                license_application=application
            ).order_by('id').first()
            if first_txn and getattr(first_txn.performed_by, 'role', None):
                forwarded_to_role = first_txn.performed_by.role
        elif stage_perms.exists():
            forwarded_to_role = stage_perms.first().role

        # Log transaction
        LicenseApplicationTransaction.objects.create(
            license_application=application,
            performed_by=user,
            forwarded_by=user,
            forwarded_to=forwarded_to_role,
            stage=target_stage,
            remarks=context_data.get("remarks")
        )
        

    @staticmethod
    @transaction.atomic
    def raise_objection(application, user, target_stage, objections, remarks=None):
        # Validate objections
        if not objections:
            raise ValidationError("No objection fields provided.")
        for obj in objections:
            if not obj.get("field") or not obj.get("remarks"):
                raise ValidationError("Each objection must include 'field' and 'remarks'.")

        # Check permissions
        if not user.is_superuser:
            if not StagePermission.objects.filter(
                stage=application.current_stage,
                role=user.role,
                can_process=True
            ).exists():
                raise PermissionError(f"Role {user.role.name} cannot raise objections in stage {application.current_stage.name}")

        # Validate transition to objection stage
        WorkflowService.validate_transition(
            workflow=application.workflow,
            from_stage=application.current_stage,
            to_stage=target_stage,
            context={"has_objections": True}
        )

        # Create objections
        for obj in objections:
            Objection.objects.create(
                application=application,
                field_name=obj["field"],
                remarks=obj["remarks"],
                raised_by=user,
                stage=target_stage
            )

        # Forward to licensee
        first_txn = LicenseApplicationTransaction.objects.filter(
            license_application=application
        ).order_by('id').first()
        if not first_txn:
            raise ValidationError("Cannot determine licensee user.")

        application.current_stage = target_stage
        application.save()

        LicenseApplicationTransaction.objects.create(
            license_application=application,
            performed_by=user,
            forwarded_by=user,
            forwarded_to=first_txn.performed_by.role,
            stage=target_stage,
            remarks=remarks or "Objection raised."
        )

    @staticmethod
    @transaction.atomic
    def resolve_objection(application, user, target_stage, context_data=None):
        # Check permissions (licensee only)
        if user.role.name != "licensee":
            raise PermissionError("Only licensee can resolve objections.")

        # Validate transition
        WorkflowService.validate_transition(
            workflow=application.workflow,
            from_stage=application.current_stage,
            to_stage=target_stage,
            context={"objections_resolved": True}
        )

        # Check if all objections are resolved
        unresolved_objections = Objection.objects.filter(application=application, is_resolved=False)
        if unresolved_objections.exists():
            raise ValidationError("Not all objections are resolved.")

        application.current_stage = target_stage
        application.save()

        forwarded_to_role = StagePermission.objects.filter(
            stage=target_stage, can_process=True
        ).first().role if StagePermission.objects.filter(stage=target_stage, can_process=True).exists() else None

        LicenseApplicationTransaction.objects.create(
            license_application=application,
            performed_by=user,
            forwarded_by=user,
            forwarded_to=forwarded_to_role,
            stage=target_stage,
            remarks=context_data.get("remarks", "Objections resolved.")
        )