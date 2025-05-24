from django.core.exceptions import ValidationError
from ..models import LicenseApplication, LicenseApplicationTransaction

def advance_application(application, user, action, remarks=""):
    """
    Advances the workflow of a license application based on the user's role, 
    current stage of the application, and the action performed.
    
    Parameters:
        application (LicenseApplication): The license application instance.
        user (User): The user performing the action.
        action (str): The action to be performed (e.g., 'approve', 'reject').
        remarks (str): Optional remarks for the action.
    
    Raises:
        ValidationError: If the action is invalid for the user's role or current stage.
    """
    role = user.role
    current_stage = application.current_stage
    action = action.lower().strip()

    # Logic for users in the 'permit_section' role
    if role == 'permit_section' and current_stage == 'permit_section':
        if action == 'forward_commissioner':
            # Forward application to the commissioner
            application.current_stage = 'commissioner'
        elif action == 'forward_joint_commissioner':
            # Forward application to the joint commissioner
            application.current_stage = 'joint_commissioner'
        elif action == 'reject':
            # Reject the application but remain in the permit_section stage
            application.current_stage = 'rejected_by_permit_section'
        else:
            raise ValidationError("Invalid action for permit_section role.")
    elif role == 'permit_section' and current_stage == 'rejected_by_permit_section':
        # Logic for re-accepting an application after rejection in permit_section
        if action == 'forward_commissioner':
            application.current_stage = 'commissioner'
        elif action == 'forward_joint_commissioner':
            application.current_stage = 'joint_commissioner'
        elif action == 'reject':
            # Raise an error for rejecting an already rejected application
            raise ValidationError("This application has already been rejected.") 
        else:
            raise ValidationError("Invalid action.") 
        
    elif role == 'permit_section' and current_stage in ['commissioner', 'joint_commissioner']:
        # Raise an error for rejecting a forwarded application
        if action == 'reject':
            raise ValidationError("This application has already forwarded.") 
        elif action in ['forward_commissioner', 'forward_joint_commissioner']:
            # Raise an error for forwarding an already forwarded application
            raise ValidationError('This application has already been forwarded.') 
        else:
            raise ValidationError("Invalid action.")

    # Logic for users in the 'commissioner' or 'joint_commissioner' roles
    elif role in ['commissioner', 'joint_commissioner'] and current_stage in ['commissioner', 'joint_commissioner']:
        if action == 'approve':
            # Approve the application and mark it as final approved
            application.current_stage = 'approved'
            application.is_approved = True
        elif action == 'reject':
            # Reject the application but remain in the current stage
            application.current_stage = f'rejected_by_{role}'
        else:
            raise ValidationError("Invalid action for commissioner or joint_commissioner.")
        
    elif role in ['commissioner', 'joint_commissioner'] and current_stage in [ 'rejected_by_commissioner', 'rejected_by_joint_commissioner']:
        if action == 'approve':       
            # Approve the application after rejection
            application.current_stage = 'approved'
            application.is_approved = True
        elif action == 'reject':
            # Raise an error for rejecting an already rejected application       
            raise ValidationError("This application has already been rejected.")
        else:
            raise ValidationError("Invalid action for commissioner or joint_commissioner.")
        
    elif role in ['commissioner', 'joint_commissioner'] and current_stage == 'approved':
        if action == 'reject':       
            # Reject the application after it was approved
            application.current_stage = f'rejected_by_{role}'
            application.is_approved = False
        elif action == 'approve':
            # Raise an error for approving an already approved application      
            raise ValidationError("This application has already been approved.")
        else:
            raise ValidationError("Invalid action for commissioner or joint_commissioner.")
    else:
        # Raise an error if the transition or user role is invalid
        raise ValidationError("Invalid transition or user not authorized for this stage.")

    # Save the updated application state
    application.save()

    # Log the transaction in the LicenseApplicationTransaction model
    LicenseApplicationTransaction.objects.create(
        license_application=application,
        performed_by=user,
        stage=application.current_stage,
        remarks=remarks
    )
