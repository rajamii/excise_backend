# helpers.py

from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator

# Validator for company name (alphabetic characters and spaces only)
def validate_name(value):
    name_validator = RegexValidator(regex=r'^[A-Za-z\s]+$', message='Name should only contain alphabets and spaces.', code='invalid_name')
    name_validator(value)

# Validator for PAN number (uppercase and alphanumeric only)
def validate_pan(value):
    pan_validator = RegexValidator(regex=r'^[A-Z0-9]+$', message='PAN number should be uppercase and alphanumeric.', code='invalid_pan')
    pan_validator(value)

# Validator for address (alphabets, numbers, and allowed punctuation)
def validate_address(value):
    address_validator = RegexValidator(regex=r'^[A-Za-z0-9\s,.-]+$', message='Address should only contain alphabets, numbers, and allowed punctuation.', code='invalid_address')
    address_validator(value)

# Validator for mobile number (10 digits, starting with 6-9)
def validate_mobile_number(value):
    mobile_validator = RegexValidator(regex=r'^[6-9]\d{9}$', message='Mobile number should be 10 digits long and start with 6-9.', code='invalid_mobile')
    mobile_validator(value)

# Validator for email format
def validate_email(value):
    email_validator = RegexValidator(regex=r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$', message='Invalid email format.', code='invalid_email')
    email_validator(value)
