from django.db import models, transaction
from django.contrib.contenttypes.fields import GenericRelation
from django.utils.timezone import now
from . import helpers
from models.masters.core.models import District , LicenseCategory ,LicenseType
from models.masters.core.models import PoliceStation, Subdivision
from auth.user.models import CustomUser
from auth.workflow.models import Workflow, WorkflowStage, Transaction, Objection


def upload_document_path(instance, filename):
    return f'license_application/{instance.application_id}/{filename}'

class LicenseApplication(models.Model):
    application_id = models.CharField(max_length=30, primary_key=True, db_index=True)
    workflow= models.ForeignKey(Workflow, on_delete=models.PROTECT, related_name='applications')
    current_stage = models.ForeignKey(WorkflowStage, on_delete=models.PROTECT, related_name='applications')

    is_approved = models.BooleanField(default=False)
    # print_count = models.PositiveIntegerField(default=0)
    # is_print_fee_paid = models.BooleanField(default=False)

    # Select License
    excise_district = models.ForeignKey(District, on_delete=models.PROTECT, related_name='license_excise_districts')
    license_category = models.ForeignKey(LicenseCategory, on_delete=models.PROTECT)
    excise_subdivision = models.ForeignKey(Subdivision, on_delete=models.PROTECT, related_name='license_excise_subdivisions')
    license = models.CharField(max_length=100)

    # Key Info
    license_type = models.ForeignKey(LicenseType, on_delete=models.PROTECT)
    establishment_name = models.CharField(max_length=255)
    mobile_number = models.BigIntegerField()
    email = models.EmailField()
    license_no = models.CharField(max_length=60, null=True, blank=True)
    initial_grant_date = models.DateField(null=True, blank=True)
    renewed_from = models.DateField(null=True, blank=True)
    valid_up_to = models.DateField(null=True, blank=True)
    yearly_license_fee = models.CharField(max_length=100, null=True, blank=True)
    license_nature = models.CharField(max_length=100)
    functioning_status = models.CharField(max_length=100)
    mode_of_operation = models.CharField(max_length=100)

    # Address
    site_subdivision = models.ForeignKey(Subdivision, on_delete=models.PROTECT, related_name='license_site_subdivisions')
    police_station = models.ForeignKey(PoliceStation, on_delete=models.PROTECT)
    location_category = models.CharField(max_length=100)
    location_name = models.CharField(max_length=100)
    ward_name = models.CharField(max_length=100)
    business_address = models.TextField()
    road_name = models.CharField(max_length=100)
    pin_code = models.IntegerField()
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)

    # Unit details
    company_name = models.CharField(max_length=255, null=True, blank=True)
    company_address = models.TextField(null=True, blank=True)
    company_pan = models.CharField(max_length=20, null=True, blank=True)
    company_cin = models.CharField(max_length=30, null=True, blank=True)
    incorporation_date = models.DateField(null=True, blank=True)
    company_phone_number = models.BigIntegerField(null=True, blank=True)
    company_email = models.EmailField(null=True, blank=True)

    # Member details
    status = models.CharField(max_length=100)
    member_name = models.CharField(max_length=100)
    father_husband_name = models.CharField(max_length=100)
    nationality = models.CharField(max_length=50)
    gender = models.CharField(max_length=10)
    pan = models.CharField(max_length=20)
    member_mobile_number = models.BigIntegerField()
    member_email = models.EmailField()

    # Document
    photo = models.ImageField(upload_to=upload_document_path)

    # Officer Actions
    is_fee_calculated = models.BooleanField(default=False)  # For Level 1

    is_license_fee_paid = models.BooleanField(default=False)

    is_license_category_updated = models.BooleanField(default=False)  # For Level 2

    applicant = models.ForeignKey(
        CustomUser,
        on_delete=models.PROTECT,
        related_name='new_license_applications'
    )

    # Polymorphic links
    transactions = GenericRelation(
        Transaction,
        content_type_field='content_type',
        object_id_field='object_id',
        related_query_name='license_application'
    )
    objections = GenericRelation(
        Objection,
        content_type_field='content_type',
        object_id_field='object_id',
        related_query_name='license_application'
    )

    def clean(self):
        if self.license_type:
            helpers.validate_license_type(self.license_type)
        helpers.validate_mobile_number(self.mobile_number)
        if self.company_phone_number is not None:
            helpers.validate_mobile_number(self.company_phone_number)
        helpers.validate_mobile_number(self.member_mobile_number)

        helpers.validate_email_field(self.email)
        if self.company_email:
            helpers.validate_email_field(self.company_email)
        helpers.validate_email_field(self.member_email)

        if self.company_pan:
            helpers.validate_pan_number(self.company_pan)
        helpers.validate_pan_number(self.pan)
        if self.company_cin:
            helpers.validate_cin_number(self.company_cin)

        helpers.validate_status(self.status)
        helpers.validate_gender(self.gender)
        helpers.validate_pin_code(self.pin_code)

        if self.latitude:
            helpers.validate_latitude(self.latitude)
        if self.longitude:
            helpers.validate_longitude(self.longitude)
    
    def save(self, *args, **kwargs):
        if not self.application_id:
            self.application_id = self.generate_application_id()
        super().save(*args, **kwargs)

    def generate_application_id(self):
        try:
            district_code = str(self.excise_district.district_code).strip()
        except AttributeError:
            raise ValueError(f"Invalid District object assigned to excise_district.")

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

            return f"LIC/{prefix}/{new_number_str}"
        
    @staticmethod
    def generate_fin_year():
        today = now().date()
        year = today.year
        month = today.month
        if month >= 4:  # April onwards → new financial year
            return f"{year}-{str(year + 1)[2:]}"
        else:
            return f"{year - 1}-{str(year)[2:]}"

    class Meta:
        db_table = 'license_application'
        indexes = [
            models.Index(fields=['excise_district']),
            models.Index(fields=['license_type']),
            models.Index(fields=['excise_subdivision']),
            models.Index(fields=['current_stage']),
            models.Index(fields=['applicant']),
        ]



