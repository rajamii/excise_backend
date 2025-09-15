# licenseapplication/helpers.py

import re
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from models.masters.core.models import LicenseType

APPLICATION_STAGES = [
    ('applicant_applied', 'Applicant Applied'),
    ('level_1', 'Level 1'),
    ('level_1_objection', 'Level 1 Objection'),
    ('level_2', 'Level 2'),
    ('level_3', 'Level 3'),
    ('level_3_objection', 'Level 3 Objection'),
    ('level_4', 'Level 4'),
    ('level_5', 'Level 5'),
    ('payment_notification', 'Payment Notification'),
    ('approved', 'Approved'),
    ('rejected', 'Rejected'),
    ('rejected_by_level_1', 'Rejected by Level 1'),
    ('rejected_by_level_2', 'Rejected by Level 2'),
    ('rejected_by_level_3', 'Rejected by Level 3'),
    ('rejected_by_level_4', 'Rejected by Level 4'),
    ('rejected_by_level_5', 'Rejected by Level 5'),
]

def validate_non_empty(value, field_name):
    if value is None or str(value).strip() == '':
        raise ValidationError(f"{field_name} cannot be empty.")
    return str(value).strip()

def validate_email_field(value):
    try:
        validate_email(value)
    except ValidationError:
        raise ValidationError("Invalid email format.")
    return value

def validate_mobile_number(value):
    if not str(value).isdigit() or len(str(value)) != 10:
        raise ValidationError("Mobile number must be a 10-digit number.")
    return value

def validate_pin_code(value):
    if not str(value).isdigit() or len(str(value)) != 6:
        raise ValidationError("PIN code must be a 6-digit number.")
    return value

def validate_pan_number(value):
    pattern = r'^[A-Z]{5}[0-9]{4}[A-Z]$'
    if not re.match(pattern, str(value)):
        raise ValidationError("Invalid PAN format (e.g., ABCDE1234F).")
    return value

def validate_cin_number(value):
    pattern = r'^[A-Z]{1}[0-9]{5}[A-Z]{2}[0-9]{4}[A-Z]{3}[0-9]{6}$'
    if not re.match(pattern, str(value)):
        raise ValidationError("Invalid CIN format.")
    return value

def validate_latitude(value):
    try:
        val = float(value)
        if not -90 <= val <= 90:
            raise ValidationError("Latitude must be between -90 and 90.")
    except ValueError:
        raise ValidationError("Latitude must be a valid float.")
    return value

def validate_longitude(value):
    try:
        val = float(value)
        if not -180 <= val <= 180:
            raise ValidationError("Longitude must be between -180 and 180.")
    except ValueError:
        raise ValidationError("Longitude must be a valid float.")
    return value

def validate_gender(value):
    if value not in ["Male", "Female", "Other"]:
        raise ValidationError("Gender must be 'Male', 'Female', or 'Other'.")
    return value

def validate_status(value):
    if value not in ["Single", "Married", "Divorced"]:
        raise ValidationError("Status must be 'Single', 'Married' or 'Divorced'.")
    return value

def validate_license_type(value):
    try:
        LicenseType.objects.get(id=value.id if hasattr(value, 'id') else value)
    except LicenseType.DoesNotExist:
        raise ValidationError("Invalid license type ID.")
    return value



