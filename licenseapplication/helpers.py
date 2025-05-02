# licenseapplication/helpers.py

import re
from django.core.exceptions import ValidationError
from django.core.validators import validate_email

def validate_non_empty(value, field_name):
    if not value or str(value).strip() == '':
        raise ValidationError(f"{field_name} cannot be empty.")
    return value

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
    if value not in ["Active", "Inactive"]:
        raise ValidationError("Status must be 'Active' or 'Inactive'.")
    return value

def validate_license_type(value):
    if value not in ["Individual", "Company"]:
        raise ValidationError("License type must be 'Individual' or 'Company'.")
    return value
