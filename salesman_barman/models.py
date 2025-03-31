from django.db import models
from django.core.exceptions import ValidationError

from .helpers import (

# choises 
    MODE_OF_OPERATION_CHOICES,
    DISTRICT_CHOICES,
    LICENSE_CATEGORY_CHOICES,
    GENDER_CHOICES,
    NATIONALITY_CHOICES,

    
# validators
    validate_pan_number,
    validate_aadhar_number,
    validate_phone_number
    validate_address,
    validate_email,
)


# Document details model
class SalesmanBarmanDocumentModel(models.Model):

    upload_path = ""
    passPhoto              = models.ImageField(upload_to=upload_path)
    aadharCard             = models.FileField(upload_to=upload_path)
    residentialCertificate = models.FileField(upload_to=upload_path)
    dateofBirthProof       = models.FileField(upload_to=upload_path)
        
    class Meta:
        db_table = 'documents_details'

    def get_upload_path(self , in_upload_path ):
        self.upload_path = in_upload_path

    def __str__(self):
        return f"Documents for {self.id}"





# Combined Salesman and Barman Details model
class SalesmanBarmanModel(models.Model):

    role              = models.CharField(max_len=10 , choices=MODE_OF_OPERATION_CHOICES)

    firstName         = models.CharField(max_length=100)
    middleName        = models.CharField(max_length=100, blank=True)
    lastName          = models.CharField(max_length=100)
    fatherHusbandName = models.CharField(max_length=100)
    gender            = models.CharField(max_length=6, choices=GENDER_CHOICES)
    dob               = models.DateField()
    nationality       = models.CharField(max_length=50, choices=NATIONALITY_CHOICES)
    address           = models.TextField(validators=[validate_address])
    pan_number        = models.CharField(max_length=10,validators=[validate_pan_number])
    aadhaar           = models.CharField(max_length=12,validators=[validate_aadhar_number])
    mobileNumber      = models.CharField(max_length=10 , validators=[validate_phone_number] )
    emailId           = models.EmailField(validators=[validate_email])
    sikkimSubject     = models.BooleanField(default=False)

    
    # License fields
    applicationYear    = models.IntegerField(choices=[(year, year) for year in range(2000, 2051)], default=2025)
    applicationId      = models.CharField(max_length=100, unique=True)
    applicationDate    = models.DateField()
    district           = models.CharField(max_length=100, choices=DISTRICT_CHOICES)
    licenseCategory   = models.CharField(max_length=100, choices=LICENSE_CATEGORY_CHOICES)
    licenseType       = models.CharField(max_length=100, choices=LICENSE_CATEGORY_CHOICES)


    
    # Foreign Key to DocumentsDetails (for document uploads)
    # documents = models.OneToOneField(DocumentsDetails, null=True, blank=True, on_delete=models.CASCADE)

    class Meta:
        db_table = 'salesman_barman_details'

    def __str__(self):
        return f"Details for {self.first_name} {self.last_name} ({self.role})"
