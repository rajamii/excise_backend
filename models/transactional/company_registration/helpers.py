import re
from django.core.exceptions import ValidationError
from django.core.validators import validate_email


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


def validate_name(value):
    """Validate that name contains only alphabets and spaces"""
    if not re.match(r'^[A-Za-z\s]+$', str(value)):
        raise ValidationError("Name should only contain alphabets and spaces.")
    return value


def validate_address(value):
    """Validate address format"""
    if not re.match(r'^[A-Za-z0-9\s,.-]+$', str(value)):
        raise ValidationError("Address should only contain alphabets, numbers, and allowed punctuation.")
    return value
