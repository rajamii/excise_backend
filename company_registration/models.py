from django.db import models
from .helpers import (  
# validators
    validate_name,
    validate_pan,
    validate_address,
    validate_email,
    validate_mobile_number
)

def upload_document_path(instance, filename):
    return f'company_registration/{instance.companyName}{' '}{instance.applicationYear}/{filename}'

class CompanyModel(models.Model):
    # Company details
    brandType = models.CharField(max_length=100, db_column='brand_type')
    license = models.CharField(max_length=100, db_column='license')
    applicationYear = models.CharField(max_length=9, default='2025-2026', db_column='application_year')    
    companyName = models.CharField(max_length=255, validators=[validate_name], db_column='company_name')
    pan = models.CharField(max_length=10, validators=[validate_pan], db_column='pan')
    officeAddress = models.TextField(validators=[validate_address], db_column='office_address')
    country = models.CharField(max_length=100, db_column='country')
    state = models.CharField(max_length=100, db_column='state')
    factoryAddress = models.TextField(validators=[validate_address], db_column='factory_address')
    pinCode = models.PositiveIntegerField(db_column='pin_code')
    companyMobileNumber = models.BigIntegerField(validators=[validate_mobile_number], db_column='company_mobile_number')
    companyEmailId = models.EmailField(validators=[validate_email], db_column='company_email_id', blank=True)

    # Member details
    memberName = models.CharField(max_length=255, validators=[validate_name], db_column='member_name')
    memberDesignation = models.CharField(max_length=255, db_column='member_designation')
    memberMobileNumber = models.BigIntegerField(validators=[validate_mobile_number], db_column='member_mobile_number')
    memberEmailId = models.EmailField(validators=[validate_email], db_column='member_email_id', blank=True)
    memberAddress = models.TextField(validators=[validate_address], db_column='member_address')

    # Payment details
    paymentId = models.CharField(max_length=100, db_column='payment_id')
    paymentDate = models.DateField(db_column='payment_date')
    paymentAmount = models.DecimalField(max_digits=10, decimal_places=2, db_column='payment_amount')
    paymentRemarks = models.TextField(blank=True, null=True, db_column='payment_remarks')

    # Document (e.g., undertaking PDF upload)
    undertaking = models.FileField(upload_to=upload_document_path)

    class Meta:
            db_table = 'company_details'

    def __str__(self):
        return f"Details for {self.company_name} ({self.application_year})"
