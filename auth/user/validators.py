import re
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

def validate_name(value: str):

    """
    Validates a given name.
    Raises ValidationError if the name is invalid.
    """
    if not isinstance(value, str):
        raise ValidationError(_("Name must be a string."))

    name = value.strip()

    if not name:
        raise ValidationError(_("Name cannot be empty."))

    # Allows alphabetic characters, spaces, and hyphens 
    # Adjust regex if other characters are needed
    
    if not re.fullmatch(r"^[a-zA-Z\s\-]+$", name):
        raise ValidationError(_("Name can only contain alphabetic characters, spaces, and hyphens."))

    if len(name) < 2:
        raise ValidationError(_("Name must be at least 2 characters long."))
    if len(name) > 50:
        raise ValidationError(_("Name cannot exceed 50 characters."))

def validate_phone_number(value: str):

    """
    Validates a given Indian phone number.
    Raises ValidationError if the phone number is invalid.
    """
    if not isinstance(value, str):
        raise ValidationError(_("Phone number must be a string."))

    phone_number = value.strip()

    # Regular expression for Indian mobile numbers:
    # ^               # Start of the string
    # [6-9]           # Must start with a digit from 6 to 9
    # \d{9}           # Followed by exactly 9 digits (0-9)
    # $               # End of the string
    indian_phone_regex = r"^[6-9]\d{9}$"

    if not re.fullmatch(indian_phone_regex, phone_number):
        raise ValidationError(_("Invalid Indian phone number format. Must be 10 digits starting with 6-9."))

