from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils import timezone
from auth.roles.models import Role
from ..models import (
    LicenseApplicationTransaction,
    SiteEnquiryReport,
    Objection,
)
from models.transactional.license.models import License

@transaction.atomic
def advance_application(application, user, remarks="", action=None, new_license_category=None, fee_amount=None, objections=None):
    # Map roles to the application stage they are authorized to act on
    role_stage_map = {
        'license': 'draft',
        'level_1': 'level_1',
        'level_2': 'level_2',
        'level_3': 'level_3',
        'level_4': 'level_4',
        'level_5': 'level_5',
    }

    # Defines how each stage progresses to the next
    stage_transitions = {
        'draft': 'applicant_applied',
        'applicant_applied': 'level_1',
        'level_1': 'level_2',
        'level_2': 'awaiting_payment',
        'awaiting_payment': 'level_3', 
        'level_3': 'level_4',
        'level_4': 'level_5',
        'level_5': 'approved',
    }

    current = application.current_stage
    role = user.role.name
    expected_stage = role_stage_map.get(role)

    # Prevent unauthorized access unless it's a rejected stage for the user's role
    is_rejected = current == f'rejected_by_{role}'
    if expected_stage != current and not is_rejected:
        raise ValidationError("User is not authorized to act on this stage.")

    if action == "reject":
        # Mark application as rejected at current role level
        application.current_stage = f"rejected_by_{role}"
        application.save()

        # Log the rejection in transaction history
        LicenseApplicationTransaction.objects.create(
            license_application=application,
            performed_by=user,
            forwarded_by=user,
            forwarded_to=None,
            stage=application.current_stage,
            remarks=remarks or "Application rejected.",
        )

    elif action == "approve":
        logical_stage = expected_stage
        constructed_remarks = remarks or ""

        # Level 1: Validate and set yearly fee
        if logical_stage == 'level_1':
            if application.is_fee_calculated:
                raise ValidationError("Fee already calculated for this application.")
            if fee_amount is None:
                raise ValidationError("Fee amount must be provided.")
            try:
                application.yearly_license_fee = str(float(fee_amount))
                application.is_fee_calculated = True
                constructed_remarks += f" Yearly License Fee set to ₹{fee_amount}"
            except ValueError:
                raise ValidationError("Invalid fee amount format.")

        # Level 2: Check if site enquiry is done and optionally update category
        elif logical_stage == 'level_2':
            if not SiteEnquiryReport.objects.filter(application=application).exists():
                raise ValidationError("Site Enquiry Report must be filled before advancing.")
            if new_license_category:
                old_category = application.license_category
                application.license_category = new_license_category
                application.is_license_category_updated = True
                constructed_remarks += (
                    f" License category changed from '{old_category}' to '{new_license_category.license_category}'"
                )

        # Move to the next defined stage
        next_stage = stage_transitions.get(logical_stage)
        if not next_stage:
            raise ValidationError("No next stage defined from current stage.")

        application.current_stage = next_stage

        # Final approval: Mark application as approved, create License record, and update license_no
        if next_stage == 'approved':
            application.is_approved = True
            # Create License record in the license app
            license = License.objects.create(
                application=application,
                license_type=application.license_type,
                establishment_name=application.establishment_name,
                licensee_name=application.member_name,
                excise_district=application.excise_district,
                issue_date=timezone.now().date(),
                valid_up_to=application.valid_up_to or (timezone.now().date() + timezone.timedelta(days=365)),
            )
            # Update LicenseApplication's license_no with generated license_id
            application.license_no = license.license_id
            constructed_remarks += f" License ID {license.license_id} generated."
            forwarded_to_role = None  # No further forwarding after approval

        # Payment stage: forward back to licensee
        elif next_stage == 'awaiting_payment':
            first_txn = LicenseApplicationTransaction.objects.filter(
                license_application=application
            ).order_by('id').first()
            if not first_txn:
                raise ValidationError("Licensee not found.")
            forwarded_to_role = first_txn.performed_by.role

        else:
            # Forward to next designated role as per stage
            forwarded_to_role = Role.objects.filter(name=next_stage).first()
            if not forwarded_to_role:
                raise ValidationError(f"No role found for next stage: {next_stage}")

        application.save()
        # Log the stage advancement
        LicenseApplicationTransaction.objects.create(
            license_application=application,
            performed_by=user,
            forwarded_by=user,
            forwarded_to=forwarded_to_role,
            stage=application.current_stage,
            remarks=constructed_remarks.strip()
        )

    elif action == "raise_objection":
        # Ensure at least one objection is passed
        if not objections:
            raise ValidationError("No objection fields provided.")

        for obj in objections:
            field = obj.get("field")
            obj_remarks = obj.get("remarks")
            if not field or not obj_remarks:
                raise ValidationError("Each objection must include both 'field' and 'remarks'.")

            # Create objection record
            Objection.objects.create(
                application=application,
                field_name=field,
                remarks=obj_remarks,
                raised_by=user
            )

        # Forward objection back to licensee
        first_txn = LicenseApplicationTransaction.objects.filter(
            license_application=application
        ).order_by('id').first()

        if not first_txn:
            raise ValidationError("Cannot determine licensee user to forward objection to.")

        licensee_user = first_txn.performed_by

        application.current_stage = f"{role}_objection"
        application.save()

        # Log objection transaction
        LicenseApplicationTransaction.objects.create(
            license_application=application,
            performed_by=user,
            forwarded_by=user,
            forwarded_to=licensee_user.role,
            stage=application.current_stage,
            remarks=remarks or "Objection raised for one or more fields."
        )

    else:
        raise ValidationError("Invalid action. Must be one of 'approve', 'reject', or 'raise_objection'.")