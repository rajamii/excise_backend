from django.core.exceptions import ValidationError
from licenseapplication.models import (
    LicenseApplication,
    LicenseApplicationTransaction,
    LocationFee,
    SiteEnquiryReport,
    Objection,
)

def advance_application(application, user, remarks="", action=None, new_license_category=None, fee_amount=None, objections=None):
    role_stage_map = {
        'license': 'draft',
        'level_1': 'level_1',
        'level_2': 'level_2',
        'level_3': 'level_3',
        'level_4': 'level_4',
        'level_5': 'level_5',
        'payment_bot': 'payment_notification',
    }

    stage_transitions = {
        'draft': 'applicant_applied',
        'applicant_applied': 'level_1',
        'level_1': 'level_2',
        'level_2': 'level_3',
        'level_3': 'level_4',
        'level_4': 'level_5',
        'level_5': 'approved',
    #   'level_5': 'payment_notification',
    #   'payment_notification': 'approved',
    }

    current = application.current_stage
    role = user.role
    expected_stage = role_stage_map.get(role)

    # Authorize only if user is at the correct stage or rejected_by_<role>
    is_rejected = current == f'rejected_by_{role}'
    if expected_stage != current and not is_rejected:
        raise ValidationError("User is not authorized to act on this stage.")

    if action == "reject":
        if role not in role_stage_map:
            raise ValidationError("Invalid user role for rejection.")
        
        application.current_stage = f"rejected_by_{role}"
        application.save()

        LicenseApplicationTransaction.objects.create(
            license_application=application,
            performed_by=user,
            stage=application.current_stage,
            remarks=remarks or "Application rejected."
        )

    elif action == "approve":
        # Treat rejection stage as the original stage for logic
        logical_stage = expected_stage if not is_rejected else expected_stage

        # Stage-specific logic
        if logical_stage == 'level_1':
            if application.fee_calculated:
                raise ValidationError("Fee already calculated for this application.")
            if fee_amount is None:
                raise ValidationError("Fee amount must be provided.")
            try:
                application.yearlyLicenseFee = str(float(fee_amount))
                application.fee_calculated = True
            except ValueError:
                raise ValidationError("Invalid fee amount format.")

        elif logical_stage == 'level_2':
            if not SiteEnquiryReport.objects.filter(application=application).exists():
                raise ValidationError("Site Enquiry Report must be filled before advancing.")
            if new_license_category:
                application.licenseCategory = new_license_category.licenseCategoryDescription
                application.license_category_updated = True

        next_stage = stage_transitions.get(logical_stage)
        if not next_stage:
            raise ValidationError("No next stage defined from current stage.")

        application.current_stage = next_stage

        if next_stage == 'approved':
            application.is_approved = True

        application.save()

        LicenseApplicationTransaction.objects.create(
            license_application=application,
            performed_by=user,
            stage=application.current_stage,
            remarks=remarks or (f"License category updated to {new_license_category}" if new_license_category else "")
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

        application.current_stage = f"{role}_objection"
        application.save()

        LicenseApplicationTransaction.objects.create(
            license_application=application,
            performed_by=user,
            stage=application.current_stage,
            remarks=remarks or "Objection raised for one or more fields."
        )

    else:
        raise ValidationError("Invalid action. Must be one of 'approve', 'reject', or 'raise_objection'.")
