from django.db import models
from .helpers import (  
    # Validators for various fields
    validate_name,
    validate_pan,
    validate_address,
    validate_email,
    validate_mobile_number
)

# Custom function to define the upload path for document uploads
def upload_document_path(instance, filename):
    return f'company_registration/{instance.companyName} {instance.applicationYear}/{filename}'

class CompanyModel(models.Model):
    # ===== Company Details =====
    brandType = models.CharField(max_length=100, db_column='brand_type')  # Type of brand (e.g., Manufacturer, Retailer)
    license = models.CharField(max_length=100, db_column='license')  # License info (could be a license number or type)
    applicationYear = models.CharField(max_length=9, default='2025-2026', db_column='application_year')  # Financial/application year
    
    companyName = models.CharField(max_length=255, validators=[validate_name], db_column='company_name')  # Company name with validation
    pan = models.CharField(max_length=10, validators=[validate_pan], db_column='pan')  # PAN number (Permanent Account Number)
    officeAddress = models.TextField(validators=[validate_address], db_column='office_address')  # Registered office address
    country = models.CharField(max_length=100, db_column='country')  # Country name
    state = models.CharField(max_length=100, db_column='state')  # State name
    factoryAddress = models.TextField(validators=[validate_address], db_column='factory_address')  # Factory address
    pinCode = models.PositiveIntegerField(db_column='pin_code')  # Pin/Zip code
    companyMobileNumber = models.BigIntegerField(validators=[validate_mobile_number], db_column='company_mobile_number')  # Company's mobile contact
    companyEmailId = models.EmailField(validators=[validate_email], db_column='company_email_id', blank=True)  # Optional company email

    # ===== Member Details =====
    memberName = models.CharField(max_length=255, validators=[validate_name], db_column='member_name')  # Contact person/member name
    memberDesignation = models.CharField(max_length=255, db_column='member_designation')  # Member's designation (e.g., Director, Manager)
    memberMobileNumber = models.BigIntegerField(validators=[validate_mobile_number], db_column='member_mobile_number')  # Member's contact number
    memberEmailId = models.EmailField(validators=[validate_email], db_column='member_email_id', blank=True)  # Optional member email
    memberAddress = models.TextField(validators=[validate_address], db_column='member_address')  # Member's residential or office address

    # ===== Payment Details =====
    paymentId = models.CharField(max_length=100, db_column='payment_id')  # Payment transaction/reference ID
    paymentDate = models.DateField(db_column='payment_date')  # Date of payment
    paymentAmount = models.DecimalField(max_digits=10, decimal_places=2, db_column='payment_amount')  # Payment amount (e.g., 15000.00)
    paymentRemarks = models.TextField(blank=True, null=True, db_column='payment_remarks')  # Optional remarks regarding payment

    # ===== Document Upload =====
    undertaking = models.FileField(upload_to=upload_document_path)  # Uploaded undertaking document (e.g., PDF)

    class Meta:
        db_table = 'company_details'  # Custom table name in the database

    def __str__(self):
        return f"Details for {self.companyName} ({self.applicationYear})"
