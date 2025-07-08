import re
from django.core.exceptions import ValidationError

# Validate phone numbers (e.g., Indian phone numbers with 10 digits)
def validate_phone_number(value):
    phone_regex = r'^[0-9]{10}$'  # Regex for 10-digit phone numbers
    if not re.match(phone_regex, value):
        raise ValidationError('Phone number must be 10 digits.')

# Validate email addresses (can add custom rules if needed)
def validate_email(value):
    if '@' not in value:
        raise ValidationError('Invalid email address.')

# Validate department names (check if it contains only alphabets and spaces)
def validate_department_name(value):
    if not all(x.isalpha() or x.isspace() for x in value):
        raise ValidationError('Department name can only contain alphabets and spaces.')

# Validate designation names (check if it contains only alphabets and spaces)
def validate_designation(value):
    if not all(x.isalpha() or x.isspace() for x in value):
        raise ValidationError('Designation name can only contain alphabets and spaces.')

# Validate that the field is not empty or null for the required fields
def validate_non_empty(value):
    if not value or value == '':
        raise ValidationError('This field cannot be empty.')

# Validate the location (HQ or District)
def validate_location(value):
    if value not in ['HQ', 'District']:
        raise ValidationError('Location must be either HQ or District.')

# Validate office level (it should be one of the predefined options)
def validate_office_level(value):
    valid_levels = ['Head Quarter', 'Permit Section', 'Administration Section', 'Accounts Section', 'IT Cell']
    if value not in valid_levels:
        raise ValidationError(f'Office level must be one of the following: {", ".join(valid_levels)}')
