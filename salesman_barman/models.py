

from django.db import models
from .helpers import (
    MODE_OF_OPERATION_CHOICES,
    LICENSE_CATEGORY_CHOICES,
    DISTRICT_CHOICES,
    GENDER_CHOICES,
    NATIONALITY_CHOICES,
    validate_pan_number,
    validate_aadhar_number,
    validate_address,
    validate_email
)
from django.core.exceptions import ValidationError

# Document details model
class DocumentsDetails(models.Model):
    passport_size_photo = models.ImageField(upload_to='documents/passport_photos/')
    aadhar_card = models.FileField(upload_to='documents/aadhar_cards/')
    sikkim_subject_certificate = models.FileField(upload_to='documents/sikkim_subject_certificates/')
    date_of_birth_proof = models.FileField(upload_to='documents/date_of_birth_proofs/')

    class Meta:
        db_table = 'documents_details'

    def __str__(self):
        return f"Documents for {self.id}"

# Combined Salesman and Barman Details model
class SalesmanBarmanDetails(models.Model):
    # Name fields
    first_name = models.CharField(max_length=100)
    middle_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100)

    # Father's/Husband's Name
    father_or_husband_name = models.CharField(max_length=100)

    # Gender
    gender = models.CharField(max_length=6, choices=GENDER_CHOICES)

    # Nationality
    nationality = models.CharField(max_length=50, choices=NATIONALITY_CHOICES)

    # Address field with validator
    address = models.TextField(validators=[validate_address])

    # PAN, Aadhar Number, Email with validators
    pan_number = models.CharField(
        max_length=10,
        validators=[validate_pan_number]
    )
    aadhar_number = models.CharField(
        max_length=12,
        validators=[validate_aadhar_number]
    )
    email = models.EmailField(validators=[validate_email])

    # Mode of operation field
    mode_of_operation = models.CharField(max_length=20, choices=MODE_OF_OPERATION_CHOICES)

    # License fields
    application_year = models.IntegerField(choices=[(year, year) for year in range(2000, 2051)], default=2025)
    application_id = models.CharField(max_length=100, unique=True)
    application_date = models.DateField()
    district = models.CharField(max_length=100, choices=DISTRICT_CHOICES)
    license_category = models.CharField(max_length=100, choices=LICENSE_CATEGORY_CHOICES)
    license_type = models.CharField(max_length=100, choices=LICENSE_CATEGORY_CHOICES)

    # Conditional Fields based on Mode of Operation
    salesman_specific_field = models.CharField(max_length=255, blank=True, null=True)
    barman_specific_field = models.CharField(max_length=255, blank=True, null=True)

    # Foreign Key to DocumentsDetails (for document uploads)
    documents = models.OneToOneField(DocumentsDetails, null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        db_table = 'salesman_barman_details'

    def __str__(self):
        return f"Details for {self.first_name} {self.last_name} ({self.mode_of_operation})"

    def clean(self):
        """
        Custom validation to ensure only relevant fields are filled depending on the mode_of_operation.
        """
        if self.mode_of_operation == 'salesman':
            if not self.salesman_specific_field:
                raise ValidationError("Salesman specific field is required for Salesman mode.")
            # You can add more validation as per requirements for the 'salesman' mode

        if self.mode_of_operation == 'barman':
            if not self.barman_specific_field:
                raise ValidationError("Barman specific field is required for Barman mode.")
            # You can add more validation as per requirements for the 'barman' mode
