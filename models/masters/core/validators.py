from django.core.exceptions import ValidationError
import re

def validate_name(value):
    if not re.match('^[a-zA-Z ]*$', value):
        raise ValidationError(f'{value} is not a valid name. Only letters and spaces are allowed.')

def validate_Numbers(value):
    if not re.match('^\d{10}$', value):  # Ensuring a 10-digit phone number
        raise ValidationError(f'{value} is not a valid phone number.')
    
def validate_name_extended(value):
    if not re.match('^[a-zA-Z0-9\s\-]*$', value):
        raise ValidationError(f'{value} is not a valid name. Only letters, numbers, spaces, and hyphens are allowed.')


