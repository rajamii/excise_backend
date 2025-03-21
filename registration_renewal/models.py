
from django.db import models
from .helpers import validate_name, validate_pan_number, validate_address, validate_mobile_number, validate_email
from masters.models import LicenseType
from .choices import APPLICATION_YEAR_CHOICES, COUNTRY_CHOICES, STATE_CHOICES

class CompanyDetails(models.Model):

    license_type = models.ForeignKey(LicenseType, on_delete=models.SET_NULL, null=True, blank=True)
    application_year = models.IntegerField(choices=APPLICATION_YEAR_CHOICES, default=2023)
    country = models.CharField(max_length=50, choices=COUNTRY_CHOICES, default='India')
    state = models.CharField(max_length=50, choices=STATE_CHOICES, default='Sikkim')

    name = models.CharField(
        max_length=100,
        validators=[validate_name]
    )

    pan_number = models.CharField(
        max_length=10,
        validators=[validate_pan_number]
    )

    registered_office_address = models.CharField(
        max_length=255,
        validators=[validate_address]
    )
    
    mobile_number = models.CharField(
        max_length=10,
        validators=[validate_mobile_number]
    )

    class Meta:
        db_table = 'company_details'

    def __str__(self):
        return self.name


class MemberDetails(models.Model):
    member_name = models.CharField(
        max_length=100,
        validators=[validate_name]
    )
    
    member_designation = models.CharField(
        max_length=100,
        validators=[validate_address]  # Assuming address validation can also be used for designation, adjust if needed.
    )
    
    mobile_number = models.CharField(
        max_length=10,
        validators=[validate_mobile_number]
    )
    
    email = models.EmailField(
        max_length=100,
        validators=[validate_email]
    )
    
    member_address = models.CharField(
        max_length=255,
        validators=[validate_address]
    )

    class Meta:
        db_table = 'member_details'

    def __str__(self):
        return self.member_name


class DocumentDetails(models.Model):
    document = models.FileField(upload_to='documents/%Y/%m/%d/', null=True, blank=True)
    payment_reference_id = models.CharField(max_length=100, unique=True)
    payment_date = models.DateField()
    remarks = models.TextField(null=True, blank=True)

    def __str__(self):
        return self.payment_reference_id
