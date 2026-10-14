from rest_framework.exceptions import PermissionDenied

ROAD_TYPE_CHOICES = (
    ('NH', 'National Highway'),
    ('SH', 'State Highway'),
    ('LINK ROAD', 'Link Road'),
)

GENDER_CHOICES = (
    ('M', 'Male'),
    ('F', 'Female'),
    ('O', 'Other'),
)

MARITAL_STATUS_CHOICES = (
    ('SINGLE',   'Single'),
    ('MARRIED',  'Married'),
    ('DIVORCED', 'Divorced'),
    ('WIDOWED',  'Widowed'),
)

RESIDENTIAL_STATUS_CHOICES = (
    ('RESIDENT',     'Resident'),
    ('NON_RESIDENT', 'Non-Resident'),
    ('OCI',          'Overseas Citizen of India'),
)

def enforce_admin_access(request):
    """Strictly enforces that only administrative roles can access this endpoint."""
    role_name = getattr(request.user.role, 'name', '').strip().lower() if getattr(request.user, 'role', None) else ''
    # Only allow Site Admin (or other explicitly authorized internal roles). Deny Licensee.
    if role_name == 'licensee':
        raise PermissionDenied("You do not have administrative privileges to update master data.")