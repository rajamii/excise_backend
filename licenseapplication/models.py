from django.db import models
from django.core.exceptions import ValidationError
from . import helpers


class LicenseApplication(models.Model):
    # Select License
    excise_district = models.CharField(max_length=100)
    license_category = models.CharField(max_length=100)
    excise_sub_division = models.CharField(max_length=100)
    license = models.CharField(max_length=100)

    # Key Info
    license_type = models.CharField(max_length=100)
    establishment_name = models.CharField(max_length=255)
    mobile_number = models.BigIntegerField()
    email_id = models.EmailField()
    license_no = models.BigIntegerField(null=True, blank=True)
    initial_grant_date = models.DateField(null=True, blank=True)
    renewed_from = models.DateField(null=True, blank=True)
    valid_up_to = models.DateField(null=True, blank=True)
    yearly_license_fee = models.CharField(max_length=100, null=True, blank=True)
    license_nature = models.CharField(max_length=100)
    functioning_status = models.CharField(max_length=100)
    modeof_operation = models.CharField(max_length=100)

    # Address
    site_sub_division = models.CharField(max_length=100)
    police_station = models.CharField(max_length=100)
    location_category = models.CharField(max_length=100)
    location_name = models.CharField(max_length=100)
    ward_name = models.CharField(max_length=100)
    business_address = models.TextField()
    road_name = models.CharField(max_length=100)
    pin_code = models.IntegerField()
    latitude = models.CharField(max_length=50, null=True, blank=True)
    longitude = models.CharField(max_length=50, null=True, blank=True)

    # Unit details
    company_name = models.CharField(max_length=255)
    company_address = models.TextField()
    company_pan = models.CharField(max_length=20)
    company_cin = models.CharField(max_length=30)
    incorporation_date = models.DateField()
    company_phone_number = models.BigIntegerField()
    company_email_id = models.EmailField()

    # Member details
    status = models.CharField(max_length=100)
    member_name = models.CharField(max_length=100)
    father_husband_name = models.CharField(max_length=100)
    nationality = models.CharField(max_length=50)
    gender = models.CharField(max_length=10)
    pan = models.BigIntegerField()
    member_mobile_number = models.BigIntegerField()
    member_email_id = models.EmailField()

    # Document
    photo = models.ImageField(upload_to='photos/')

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
