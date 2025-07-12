from django.db import transaction
from django.core.exceptions import ValidationError
from typing import Optional
from auth.user.models import CustomUser
from auth.roles.models import Role
from ..models import (
    LicenseApplication,
    LicenseApplicationTransaction,
    LocationFee,
    SiteEnquiryReport,
    Objection,
)

@transaction.atomic
def advance_application(application, user, remarks="", action=None, new_license_category=None, fee_amount=None, objections=None):
    role_stage_map = {
        'license': 'draft',
        'level_1': 'level_1',
        'level_2': 'level_2',
        'level_3': 'level_3',
        'level_4': 'level_4',
        'level_5': 'level_5',
    }

    stage_transitions = {
        'draft': 'applicant_applied',
        'applicant_applied': 'level_1',
        'level_1': 'level_2',
        'level_2': 'level_3',
        'level_3': 'level_4',
        'level_4': 'level_5',
        'level_5': 'approved',
    }

    current = application.current_stage
    role = user.role.name
    expected_stage = role_stage_map.get(role)

    is_rejected = current == f'rejected_by_{role}'
    if expected_stage != current and not is_rejected:
        raise ValidationError("User is not authorized to act on this stage.")

    if action == "reject":
        application.current_stage = f"rejected_by_{role}"
        application.save()

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

        next_stage = stage_transitions.get(logical_stage)
        if not next_stage:
            raise ValidationError("No next stage defined from current stage.")

        # ✅ Get Role for forwarded_to
        forwarded_to_role = Role.objects.filter(name=next_stage).first()
        if not forwarded_to_role:
            raise ValidationError(f"No role found for next stage: {next_stage}")

        application.current_stage = next_stage
        if next_stage == 'approved':
            application.is_approved = True
        application.save()

        LicenseApplicationTransaction.objects.create(
            license_application=application,
            performed_by=user,
            forwarded_by=user,
            forwarded_to=forwarded_to_role,
            stage=application.current_stage,
            remarks=constructed_remarks.strip()
        )

    elif action == "raise_objection":
        if not objections:
            raise ValidationError("No objection fields provided.")

        for obj in objections:
            field = obj.get("field")
            obj_remarks = obj.get("remarks")
            if not field or not obj_remarks:
                raise ValidationError("Each objection must include both 'field' and 'remarks'.")

            Objection.objects.create(
                application=application,
                field_name=field,
                remarks=obj_remarks,
                raised_by=user
            )

        # Get the licensee from the first transaction (applicant)
        first_txn = LicenseApplicationTransaction.objects.filter(
            license_application=application
        ).order_by('id').first()

        if not first_txn:
            raise ValidationError("Cannot determine licensee user to forward objection to.")

        licensee_user = first_txn.performed_by

        application.current_stage = f"{role}_objection"
        application.save()

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
