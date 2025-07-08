from django.db import models
from django.core.exceptions import ValidationError
from .helpers import (
    validate_pan_number,
    validate_aadhaar_number,
    validate_phone_number,
    validate_address,
    validate_email,
)

def upload_document_path(instance, filename):
    return f'salesman_barman_registration/{instance.role} {instance.firstName} {instance.lastName}/{filename}'

class SalesmanBarmanModel(models.Model):
    ROLE_CHOICES = [
        ('Salesman', 'Salesman'),
        ('Barman', 'Barman'),
    ]
    
    GENDER_CHOICES = [
        ('Male', 'Male'),
        ('Female', 'Female'),
        ('Other', 'Other'),
    ]

    # Basic identity info
    role = models.CharField(
        max_length=10,
        choices=ROLE_CHOICES
    )

    # Personal details
    firstName = models.CharField(max_length=100, db_column='first_name')
    middleName = models.CharField(
        max_length=100,
        blank=True,
        db_column='middle_name'
    )
    lastName = models.CharField(max_length=100, db_column='last_name')
    fatherHusbandName = models.CharField(
        max_length=100,
        db_column='father_husband_name'
    )
    gender = models.CharField(
        max_length=6,
        choices=GENDER_CHOICES
    )
    dob = models.DateField()
    nationality = models.CharField(max_length=50, default='Indian')
    address = models.TextField(validators=[validate_address])

    # Identity verification
    pan = models.CharField(
        max_length=10,
        validators=[validate_pan_number]
    )
    aadhaar = models.CharField(
        max_length=12,
        validators=[validate_aadhaar_number]
    )
    mobileNumber = models.CharField(
        max_length=10,
        validators=[validate_phone_number],
        db_column='mobile_number'
    )
    emailId = models.EmailField(
        blank=True,
        validators=[validate_email],
        db_column='email_id'
    )
    sikkimSubject = models.BooleanField(
        default=False,
        db_column='sikkim_subject'
    )

    # License and application-related fields
    applicationYear = models.CharField(
        max_length=9,
        default='2025-2026',
        db_column='application_year'
    )
    applicationId = models.CharField(
        max_length=100,
        unique=True,
        db_column='application_id'
    )
    applicationDate = models.DateField(db_column='application_date')
    district = models.CharField(max_length=100)
    licenseCategory = models.CharField(
        max_length=100,
        db_column='license_category'
    )
    license = models.CharField(max_length=100, db_column='license')

    # Uploaded documents
    passPhoto = models.ImageField(
        upload_to=upload_document_path,
        db_column='pass_photo'
    )
    aadhaarCard = models.FileField(
        upload_to=upload_document_path,
        db_column='aadhaar_card'
    )
    residentialCertificate = models.FileField(
        upload_to=upload_document_path,
        db_column='residential_certificate'
    )
    dateofBirthProof = models.FileField(
        upload_to=upload_document_path,
        db_column='dateof_birth_proof'
    )
    
    # Soft delete field
    IsActive = models.BooleanField(
        default=True,
        db_column='is_active'
    )

    class Meta:
        db_table = 'salesman_barman_details'
        verbose_name = 'Salesman/Barman Registration'
        verbose_name_plural = 'Salesmen/Barmen Registrations'

    def __str__(self):
        return f"{self.role}: {self.firstName} {self.lastName} ({self.applicationId})"
