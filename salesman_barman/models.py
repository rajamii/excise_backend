from django.db import models
from django.core.exceptions import ValidationError
from .helpers import (  
    # Custom validators for various fields
    validate_pan_number,
    validate_aadhaar_number,
    validate_phone_number,
    validate_address,
    validate_email,
)

# Custom function to define the file upload path for all documents
def upload_document_path(instance, filename):
    return f'salesman_barman_registration/{instance.role} {instance.firstName} {instance.lastName}/{filename}'


# Model: SalesmanBarmanModel
# Stores registration details for salesman or barman roles
class SalesmanBarmanModel(models.Model):

    # Basic identity info
    role = models.CharField(max_length=10)  # Either 'Salesman' or 'Barman'

    # Personal details
    firstName = models.CharField(max_length=100, db_column='first_name')  # First name
    middleName = models.CharField(max_length=100, blank=True, db_column='middle_name')  # Optional middle name
    lastName = models.CharField(max_length=100, db_column='last_name')  # Last name
    fatherHusbandName = models.CharField(max_length=100, db_column='father_husband_name')  # Father's or husband's name
    gender = models.CharField(max_length=6)  # Gender field (e.g., Male/Female/Other)
    dob = models.DateField()  # Date of birth
    nationality = models.CharField(max_length=50)  # Citizenship
    address = models.TextField(validators=[validate_address])  # Full residential address

    # Identity verification
    pan = models.CharField(max_length=10, validators=[validate_pan_number])  # PAN number (10 characters)
    aadhaar = models.CharField(max_length=12, validators=[validate_aadhaar_number])  # Aadhaar number (12 digits)
    mobileNumber = models.CharField(max_length=10, validators=[validate_phone_number], db_column='mobile_number')  # Mobile contact
    emailId = models.EmailField(blank=True, validators=[validate_email], db_column='email_id')  # Optional email
    sikkimSubject = models.BooleanField(default=False, db_column='sikkim_subject')  # Checkbox: Is a subject of Sikkim?

    # License and application-related fields
    applicationYear = models.CharField(max_length=9, default='2025-2026', db_column='application_year')  # Fiscal/application year
    applicationId = models.CharField(max_length=100, unique=True, db_column='application_id')  # Unique application ID
    applicationDate = models.DateField(db_column='application_date')  # Date of application submission
    district = models.CharField(max_length=100)  # District name
    licenseCategory = models.CharField(max_length=100, db_column='license_category')  # License category (e.g., Bar, Wholesale)
    license = models.CharField(max_length=100, db_column='license')  # License number or ID

    # Uploaded documents
    passPhoto = models.ImageField(upload_to=upload_document_path, db_column='pass_photo')  # Passport-size photograph
    aadhaarCard = models.FileField(upload_to=upload_document_path, db_column='aadhaar_card')  # Aadhaar card copy
    residentialCertificate = models.FileField(upload_to=upload_document_path, db_column='residential_certificate')  # Proof of residence
    dateofBirthProof = models.FileField(upload_to=upload_document_path, db_column='dateof_birth_proof')  # DOB proof document

    class Meta:
        db_table = 'salesman_barman_details'  # Custom table name in the DB

    def __str__(self):
        # String representation of the object (useful in admin panel and debugging)
        return f"Details for {self.first_name} {self.last_name} ({self.role})"
