from django.db import models
from .choices import LICENSE_TYPE_CHOICES, APPLICATION_YEAR_CHOICES, COUNTRY_CHOICES, STATE_CHOICES

class CompanyDetails(models.Model):
    # Fields for company details model
    license_type = models.CharField(max_length=50, choices=LICENSE_TYPE_CHOICES, default='Retail')
    application_year = models.IntegerField(choices=APPLICATION_YEAR_CHOICES, default=2023)
    country = models.CharField(max_length=50, choices=COUNTRY_CHOICES, default='India')
    state = models.CharField(max_length=50, choices=STATE_CHOICES, default='Maharashtra')
    name = models.CharField(max_length=100)
    pan_number = models.CharField(max_length=10)
    registered_office_address = models.CharField(max_length=255)
    mobile_number = models.CharField(max_length=15)

    # You can add other fields as necessary
    class Meta:
        db_table = 'company_details'  # Table name will be 'company_details'

    def __str__(self):
        return self.name

class MemberDetails(models.Model):
    member_name = models.CharField(max_length=100)
    member_designation = models.CharField(max_length=100)
    mobile_number = models.CharField(max_length=15)
    email = models.EmailField(max_length=100)
    member_address = models.CharField(max_length=255)

    class Meta:
        db_table = 'member_details'  # Table name will be 'member_details'

    def __str__(self):
        return self.member_name

class DocumentDetails(models.Model):
    # Upload document field
    document = models.FileField(upload_to='documents/%Y/%m/%d/', null=True, blank=True)  # Save the uploaded files in a folder
    
    # Payment reference ID field
    payment_reference_id = models.CharField(max_length=100, unique=True)

    # Payment date (select option - DateField with a dropdown)
    payment_date = models.DateField()

    # Remarks field
    remarks = models.TextField(null=True, blank=True)

    def __str__(self):
        return self.payment_reference_id