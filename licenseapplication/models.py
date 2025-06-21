from django.db import models, transaction
from django.core.exceptions import ValidationError
from django.utils.timezone import now
from . import helpers

def upload_document_path(instance, filename):
    return f'license_application/{instance.application_id}/{filename}'

def upload_level2_document_path(instance, filename):
    return f'license_application/{instance.application_id}/level2_docs/{filename}'

class LicenseApplication(models.Model):

    application_id = models.CharField(max_length=30, primary_key=True, db_index=True)

    # Select License
    exciseDistrict = models.CharField(max_length=100, db_column='excise_district')
    licenseCategory = models.CharField(max_length=100, db_column='license_category')
    exciseSubDivision = models.CharField(max_length=100, db_column='excise_sub_division')
    license = models.CharField(max_length=100)

    # Key Info
    licenseType = models.CharField(max_length=100, db_column='license_type')
    establishmentName = models.CharField(max_length=255, db_column='establishment_name')
    mobileNumber = models.BigIntegerField(db_column='mobile_number')
    emailId = models.EmailField(db_column='email_id')
    licenseNo = models.BigIntegerField(null=True, blank=True, db_column='license_no')
    initialGrantDate = models.DateField(null=True, blank=True, db_column='initial_grant_date')
    renewedFrom = models.DateField(null=True, blank=True, db_column='renewed_from')
    validUpTo = models.DateField(null=True, blank=True, db_column='valid_up_to')
    yearlyLicenseFee = models.CharField(max_length=100, null=True, blank=True, db_column='yearly_license_fee')
    licenseNature = models.CharField(max_length=100, db_column='license_nature')
    functioningStatus = models.CharField(max_length=100, db_column='functioning_status')
    modeofOperation = models.CharField(max_length=100, db_column='mode_of_operation')

    # Address
    siteSubDivision = models.CharField(max_length=100, db_column='site_sub_division')
    policeStation = models.CharField(max_length=100, db_column='police_station')
    locationCategory = models.CharField(max_length=100, db_column='location_category')
    locationName = models.CharField(max_length=100, db_column='location_name')
    wardName = models.CharField(max_length=100, db_column='ward_name')
    businessAddress = models.TextField(db_column='business_address')
    roadName = models.CharField(max_length=100, db_column='road_name')
    pinCode = models.IntegerField(db_column='pin_code')
    latitude = models.CharField(max_length=50, null=True, blank=True, db_column='latitude')
    longitude = models.CharField(max_length=50, null=True, blank=True, db_column='longitude')

    # Unit details
    companyName = models.CharField(max_length=255, null=True, blank=True, db_column='company_name')
    companyAddress = models.TextField(null=True, blank=True, db_column='company_address')
    companyPan = models.CharField(max_length=20, null=True, blank=True, db_column='company_pan')
    companyCin = models.CharField(max_length=30, null=True, blank=True, db_column='company_cin')
    incorporationDate = models.DateField(null=True, blank=True, db_column='incorporation_date')
    companyPhoneNumber = models.BigIntegerField(null=True, blank=True, db_column='company_phone_number')
    companyEmailId = models.EmailField(null=True, blank=True, db_column='company_email_id')

    # Member details
    status = models.CharField(max_length=100)
    memberName = models.CharField(max_length=100, db_column='member_name')
    fatherHusbandName = models.CharField(max_length=100, db_column='father_husband_name')
    nationality = models.CharField(max_length=50)
    gender = models.CharField(max_length=10)
    pan = models.CharField()
    memberMobileNumber = models.BigIntegerField(db_column='member_mobile_number')
    memberEmailId = models.EmailField(db_column='member_email_id')

    # Document
    photo = models.ImageField(upload_to=upload_document_path)

    current_stage = models.CharField(
        max_length=30,
        choices=[
            ('draft', 'Draft'),
            ('applicant_applied', 'Applicant Applied'),
            ('level_1', 'Level 1'),
            ('level_1_objection', 'Level 1 Objection'),
            ('level_2', 'Level 2'),
            ('level_3', 'Level 3'),
            ('level_3_objection', 'Level 3 Objection'),
            ('level_4', 'Level 4'),
            ('level_5', 'Level 5'),
            ('payment_notification', 'Payment Notification'),
            ('approved', 'Approved'),
            ('rejected', 'Rejected'),
        ],
        default='draft'
    )

    is_approved = models.BooleanField(default=False)

    # New fields for print tracking
    print_count = models.PositiveIntegerField(default=0)
    print_fee_paid = models.BooleanField(default=False)

    # Officer Actions
    fee_calculated = models.BooleanField(default=False)  # For Level 1
    license_category_updated = models.BooleanField(default=False)  # For Level 2


    def can_print_license(self):
        if self.print_count < 5:
            return True, 0  # Allowed to print, no fee required
        elif self.print_fee_paid:
            return True, 500  # Allowed to print, fee has been paid
        else:
            return False, 500  # Not allowed, fee required

    def record_license_print(self, fee_paid=False):
        self.print_count += 1
        if self.print_count > 5 and fee_paid:
            self.print_fee_paid = True
        self.save()

    def clean(self):
        helpers.validate_license_type(self.licenseType)
        helpers.validate_mobile_number(self.mobileNumber)
        if self.companyPhoneNumber is not None:
            helpers.validate_mobile_number(self.companyPhoneNumber)
        helpers.validate_mobile_number(self.memberMobileNumber)

        helpers.validate_email_field(self.emailId)
        if self.companyEmailId:
            helpers.validate_email_field(self.companyEmailId)
        helpers.validate_email_field(self.memberEmailId)

        if self.companyPan:
            helpers.validate_pan_number(self.companyPan)
        helpers.validate_pan_number(self.pan)
        if self.companyCin:
            helpers.validate_cin_number(self.companyCin)

        helpers.validate_status(self.status)
        helpers.validate_gender(self.gender)
        helpers.validate_pin_code(self.pinCode)

        if self.latitude:
            helpers.validate_latitude(self.latitude)
        if self.longitude:
            helpers.validate_longitude(self.longitude)
    
    def save(self, *args, **kwargs):
        if not self.application_id:
            self.application_id = self.generate_application_id()
        super().save(*args, **kwargs)

    def generate_application_id(self):
        district_code = self.exciseDistrict.strip()

        today = now().date()
        year = today.year
        month = today.month
        if month >= 4:
            fin_year = f"{year}-{str(year + 1)[2:]}"
        else:
            fin_year = f"{year - 1}-{str(year)[2:]}"

        prefix = f"{district_code}/{fin_year}"

        with transaction.atomic():
            last_app = LicenseApplication.objects.filter(
                application_id__startswith=prefix
            ).order_by('-application_id').first()

            if last_app and last_app.application_id:
                last_number_str = last_app.application_id.split('/')[-1]
                try:
                    last_number = int(last_number_str)
                except ValueError:
                    last_number = 0
            else:
                last_number = 0

            new_number = last_number + 1
            new_number_str = str(new_number).zfill(4)

            return f"{prefix}/{new_number_str}"


    class Meta:
        db_table = 'license_application'

class LocationFee(models.Model):
    location_name = models.CharField(max_length=100, unique=True)
    fee_amount = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        db_table = 'location_fee'

    def __str__(self):
        return f"{self.location_name} - ₹{self.fee_amount}"


class LicenseApplicationTransaction(models.Model):
    STAGES = [
        ('applicant_applied', 'Applicant Applied'),
        ('level_1', 'Level 1'),
        ('level_1_objection', 'Level 1 Objection'),
        ('level_2', 'Level 2'),
        ('level_3', 'Level 3'),
        ('level_3_objection', 'Level 3 Objection'),
        ('level_4', 'Level 4'),
        ('level_5', 'Level 5'),
        ('payment_notification', 'Payment Notification'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]

    license_application = models.ForeignKey(
        LicenseApplication, on_delete=models.CASCADE, related_name='transactions'
    )
    performed_by = models.ForeignKey(
        'user.CustomUser', on_delete=models.SET_NULL, null=True, related_name='performed_transactions'
    )
    forwarded_by = models.ForeignKey(
        'user.CustomUser', on_delete=models.SET_NULL, null=True, related_name='forwarded_by_transactions'
    )
    forwarded_to = models.ForeignKey(
        'user.CustomUser', on_delete=models.SET_NULL, null=True, related_name='forwarded_to_transactions'
    )
    stage = models.CharField(max_length=30, choices=STAGES)
    remarks = models.TextField(blank=True, null=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'license_application_transaction'
        ordering = ['timestamp']

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.license_application.current_stage != self.stage:
            self.license_application.current_stage = self.stage
            self.license_application.save(update_fields=['current_stage']) 


class SiteEnquiryReport(models.Model):

    application = models.OneToOneField(
        LicenseApplication, 
        on_delete=models.CASCADE, 
        related_name='site_enquiry_report')

    # Worship
    hasTraditionalPlace = models.BooleanField(db_column='has_traditional_place')
    traditionalPlaceDistance = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, db_column='traditional_place_distance')
    traditionalPlaceName = models.CharField(max_length=1000, blank=True, db_column='traditional_place_name')
    traditionalPlaceNature = models.CharField(max_length=1000, blank=True, db_column='traditional_place_nature')
    traditionalPlaceConstruction = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        choices=[('rcc', 'RCC'), ('wooden_structure', 'Wooden Structure'), ('temporary', 'Temporary')],
        db_column='traditional_place_construction'
    )

    # Education
    hasEducationalInstitution = models.BooleanField(db_column='has_educational_institution')
    educationalInstitutionDistance = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, db_column='educational_institution_distance')
    educationalInstitutionName = models.CharField(max_length=1000, blank=True, db_column='educational_institution_name')
    educationalInstitutionNature = models.CharField(max_length=1000, blank=True, db_column='educational_institution_nature')

    # Hospital
    hasHospital = models.BooleanField(db_column='has_hospital')
    hospitalDistance = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, db_column='hospital_distance')
    hospitalName = models.CharField(max_length=1000, blank=True, db_column='hospital_name')

    # Taxi Stand
    hasTaxiStand = models.BooleanField(db_column='has_taxi_stand')
    taxiStandName = models.CharField(max_length=1000, blank=True, db_column='taxi_stand_name')
    taxiStandDistance = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, db_column='taxi_stand_distance')

    # Connectivity
    isInterconnectedWithShops = models.BooleanField(db_column='is_interconnected_with_shops')
    interconnectivityRemarks = models.TextField(max_length=1000, blank=True, db_column='interconnectivity_remarks')

    # Comments
    enquiryOfficerComments = models.TextField(max_length=2000, blank=True, db_column='enquiry_officer_comments')

    # Other enquiry points
    shopConstructionType = models.CharField(
        max_length=100,
        choices=[('rcc', 'RCC'), ('wooden_structure', 'Wooden Structure'), ('temporary', 'Temporary')],
        db_column='shop_construction_type'
    )
    hasExciseShopsNearby = models.BooleanField(db_column='has_excise_shops_nearby')
    nearbyExciseShopCount = models.IntegerField(default=0, db_column='nearby_excise_shop_count')
    nearbyExciseShopsRemarks = models.TextField(max_length=2000, blank=True, db_column='nearby_excise_shops_remarks')

    isOnHighway = models.BooleanField(db_column='is_on_highway')
    highwayName = models.TextField(max_length=2000, blank=True, db_column='highway_name')

    shopImageDocument = models.FileField(upload_to='site_enquiry/', null=True, blank=True, db_column='shop_image_document')

    latitude = models.FloatField(blank=True, null=True, db_column='latitude')
    longitude = models.FloatField(blank=True, null=True, db_column='longitude')

    isShopSizeCorrect = models.BooleanField(db_column='is_shop_size_correct')
    shopSizeRemarks = models.TextField(max_length=2000, blank=True, db_column='shop_size_remarks')

    additionalEnquiryOfficerComments = models.TextField(max_length=2000, blank=True, db_column='additional_enquiry_officer_comments')

    # Document verifications with comments
    hasIdProof = models.BooleanField(db_column='has_id_proof')
    idProofComments = models.TextField(max_length=1000, blank=True, db_column='id_proof_comments')

    hasAgeProof = models.BooleanField(db_column='has_age_proof')
    ageProofComments = models.TextField(max_length=1000, blank=True, db_column='age_proof_comments')

    hasNocFromLandlord = models.BooleanField(db_column='has_noc_from_landlord')
    nocComments = models.TextField(max_length=1000, blank=True, db_column='noc_comments')

    hasOwnershipProof = models.BooleanField(db_column='has_ownership_proof')
    ownershipProofComments = models.TextField(max_length=1000, blank=True, db_column='ownership_proof_comments')

    hasTradeLicense = models.BooleanField(db_column='has_trade_license')
    tradeLicenseComments = models.TextField(max_length=1000, blank=True, db_column='trade_license_comments')

    proposesBarmanOrSalesman = models.BooleanField(db_column='proposes_barman_or_salesman')
    workerProposalComments = models.TextField(max_length=1000, blank=True, db_column='worker_proposal_comments')

    workerDocsValid = models.BooleanField(db_column='worker_docs_valid')
    workerDocsComments = models.TextField(max_length=1000, blank=True, db_column='worker_docs_comments')

    licenseRecommendation = models.BooleanField(db_column='license_recommendation')
    recommendationComments = models.TextField(max_length=1000, blank=True, db_column='recommendation_comments')

    specialRemarks = models.TextField(max_length=2000, blank=True, db_column='special_remarks')
    reportingPlace = models.CharField(max_length=250, blank=True, db_column='reporting_place')

    #report_file = models.FileField(upload_to='site_enquiry_reports/')
    #remarks = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'site_enquiry_report'
        ordering = ['created_at']

    def __str__(self):
        return f"Site Enquiry Report for Application {self.application.application_id}"
    
class Objection(models.Model):
    application = models.ForeignKey(LicenseApplication, on_delete=models.CASCADE)
    field_name = models.CharField(max_length=255, db_index=True)
    remarks = models.TextField()
    raised_by = models.ForeignKey('user.CustomUser', on_delete=models.SET_NULL, null=True)
    resolved = models.BooleanField(default=False, db_index=True)
    raised_on = models.DateTimeField(auto_now_add=True)
    resolved_on = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'license_application_objection'
        ordering = ['raised_on']
 

