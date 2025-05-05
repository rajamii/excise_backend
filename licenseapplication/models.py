from django.db import models
from django.core.exceptions import ValidationError
from . import helpers

def upload_document_path(instance, filename):
    return f'license_application/{instance.id}/{filename}'

class LicenseApplication(models.Model):
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

    def clean(self):
        # Field-level validations using helpers
        helpers.validate_license_type(self.license_type)
        helpers.validate_mobile_number(self.mobile_number)
        helpers.validate_mobile_number(self.company_phone_number)
        helpers.validate_mobile_number(self.member_mobile_number)

        helpers.validate_email_field(self.email_id)
        helpers.validate_email_field(self.company_email_id)
        helpers.validate_email_field(self.member_email_id)

        helpers.validate_pan_number(self.company_pan)
        helpers.validate_pan_number(self.pan)
        helpers.validate_cin_number(self.company_cin)

        helpers.validate_status(self.status)
        helpers.validate_gender(self.gender)
        helpers.validate_pin_code(self.pin_code)

        if self.latitude:
            helpers.validate_latitude(self.latitude)

        if self.longitude:
            helpers.validate_longitude(self.longitude)

    class Meta:
        db_table = 'license_application'
