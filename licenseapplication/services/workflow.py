from django.core.exceptions import ValidationError
from ..models import LicenseApplication, LicenseApplicationTransaction

def advance_application(application, user, remarks=""):
    if user.role == 'permit_section' and application.current_stage == 'draft':
        application.current_stage = 'permit_section'

    elif user.role == 'joint_commissioner' and application.current_stage == 'permit_section':
        application.current_stage = 'joint_commissioner'

    elif user.role == 'commissioner' and application.current_stage == 'joint_commissioner':
        application.current_stage = 'approved'
        application.is_approved = True

    else:
        raise ValidationError("Invalid transition or user not authorized for this stage.")

    application.save()

    LicenseApplicationTransaction.objects.create(
        license_application=application,
        performed_by=user,
        stage=application.current_stage,
        remarks=remarks
    )
