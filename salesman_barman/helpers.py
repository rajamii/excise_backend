# helpers.py

from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator, EmailValidator, MaxLengthValidator

# Choices for Mode of Operation
MODE_OF_OPERATION_CHOICES = [
    ('salesman', 'Salesman'),
    ('barman', 'Barman'),
]

# Choices for License Category
LICENSE_CATEGORY_CHOICES = [
    ('type_a', 'Type A'),
    ('type_b', 'Type B'),
    ('type_c', 'Type C'),
]

# Choices for District
DISTRICT_CHOICES = [
    ('district_1', 'District 1'),
    ('district_2', 'District 2'),
    ('district_3', 'District 3'),
]

# Choices for Gender
GENDER_CHOICES = [
    ('male', 'Male'),
    ('female', 'Female'),
]

# Choices for Nationality
NATIONALITY_CHOICES = [
    ('indian', 'Indian'),
    ('other', 'Other'),
]

# Validators for fields
def validate_pan_number(value):
    pan_validator = RegexValidator(r'^[A-Z]{5}[0-9]{4}[A-Z]{1}$', 'Invalid PAN format')
    pan_validator(value)

def validate_aadhar_number(value):
    aadhar_validator = RegexValidator(r'^\d{12}$', 'Aadhar number must be 12 digits')
    aadhar_validator(value)

def validate_phone_number(value):
    phone_validator = RegexValidator(r'^[0-9]+$', 'Phone number must consist only digits from 0 to 9 ' )
    phone_validator(value)

def validate_address(value):
    address_validator = MaxLengthValidator(500)
    address_validator(value)

def validate_email(value):
    email_validator = EmailValidator()
    email_validator(value)
