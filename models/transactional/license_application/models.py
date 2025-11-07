from django.db import models, transaction
from django.utils.timezone import now
from . import helpers
from models.masters.core.models import District , LicenseCategory ,LicenseType
from models.masters.core.models import PoliceStation, Subdivision
from auth.user.models import CustomUser
from auth.roles.models import Role
from auth.workflow.models import Workflow, WorkflowStage


def upload_document_path(instance, filename):
    return f'license_application/{instance.application_id}/{filename}'

class LicenseApplication(models.Model):
    application_id = models.CharField(max_length=30, primary_key=True, db_index=True)
    workflow= models.ForeignKey(Workflow, on_delete=models.PROTECT, related_name='applications')
    current_stage = models.ForeignKey(WorkflowStage, on_delete=models.PROTECT, related_name='applications')

    is_approved = models.BooleanField(default=False)
    print_count = models.PositiveIntegerField(default=0)
    is_print_fee_paid = models.BooleanField(default=False)

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

    def can_print_license(self):
        if self.print_count < 5:
            return True, 0  # Allowed to print, no fee required
        elif self.is_print_fee_paid:
            return True, 500  # Allowed to print, fee has been paid
        else:
            return False, 500  # Not allowed, fee required

    def record_license_print(self, fee_paid=False):
        self.print_count += 1
        if self.print_count > 5 and fee_paid:
            self.is_print_fee_paid = True
        self.save()

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

            return f"{prefix}/{new_number_str}"

    class Meta:
        db_table = 'license_application'
        indexes = [
            models.Index(fields=['excise_district']),
            models.Index(fields=['license_type']),
            models.Index(fields=['excise_subdivision']),
            models.Index(fields=['current_stage']),
        ]

class LicenseApplicationTransaction(models.Model):
    license_application = models.ForeignKey(LicenseApplication, on_delete=models.CASCADE, related_name='transactions')
    performed_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, related_name='performed_transactions')
    forwarded_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, related_name='forwarded_by_transactions')
    forwarded_to = models.ForeignKey(Role, on_delete=models.SET_NULL, null=True, related_name='forwarded_to_transactions')
    stage = models.ForeignKey(WorkflowStage, on_delete=models.PROTECT, related_name='transactions')
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

class Objection(models.Model):
    application = models.ForeignKey(LicenseApplication, on_delete=models.CASCADE, related_name='objections')
    field_name = models.CharField(max_length=255, db_index=True)
    remarks = models.TextField()
    raised_by = models.ForeignKey('user.CustomUser', on_delete=models.SET_NULL, null=True, related_name='license_objections')
    stage = models.ForeignKey('workflow.WorkflowStage', on_delete=models.SET_NULL, null=True, related_name='license_objection_stage')
    is_resolved = models.BooleanField(default=False, db_index=True)
    raised_on = models.DateTimeField(auto_now_add=True)
    resolved_on = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'license_application_objection'
        ordering = ['raised_on']


class LocationFee(models.Model):
    location_name = models.CharField(max_length=100, unique=True)
    fee_amount = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        db_table = 'location_fee'

    def __str__(self):
        return f"{self.location_name} - ₹{self.fee_amount}"


class SiteEnquiryReport(models.Model):
    application = models.OneToOneField(
        LicenseApplication, 
        on_delete=models.CASCADE, 
        related_name='site_enquiry_report')

    # Worship
    has_traditional_place = models.BooleanField()
    traditional_place_distance = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    traditional_place_name = models.CharField(max_length=1000, blank=True)
    traditional_place_nature = models.CharField(max_length=1000, blank=True)
    traditional_place_construction = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        choices=[('rcc', 'RCC'), ('wooden_structure', 'Wooden Structure'), ('temporary', 'Temporary')],
    )

    # Education
    has_educational_institution = models.BooleanField()
    educational_institution_distance = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    educational_institution_name = models.CharField(max_length=1000, blank=True)
    educational_institution_nature = models.CharField(max_length=1000, blank=True)

    # Hospital
    has_hospital = models.BooleanField()
    hospital_distance = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    hospital_name = models.CharField(max_length=1000, blank=True)

    # Taxi Stand
    has_taxi_stand = models.BooleanField()
    taxi_stand_name = models.CharField(max_length=1000, blank=True)
    taxi_stand_distance = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    # Connectivity
    is_interconnected_with_shops = models.BooleanField()
    interconnectivity_remarks = models.TextField(max_length=1000, blank=True)

    # Comments
    enquiry_officer_comments = models.TextField(max_length=2000, blank=True)

    # Other enquiry points
    shop_construction_type = models.CharField(
        max_length=100,
        choices=[('rcc', 'RCC'), ('wooden_structure', 'Wooden Structure'), ('temporary', 'Temporary')],
    )
    has_excise_shops_nearby = models.BooleanField()
    nearby_excise_shop_count = models.IntegerField(default=0)
    nearby_excise_shops_remarks = models.TextField(max_length=2000, blank=True)

    is_on_highway = models.BooleanField()
    highway_name = models.TextField(max_length=2000, blank=True)

    shop_image_document = models.FileField(upload_to=upload_document_path)

    latitude = models.FloatField(blank=True, null=True)
    longitude = models.FloatField(blank=True, null=True)

    is_shop_size_correct = models.BooleanField()
    shop_size_remarks = models.TextField(max_length=2000, blank=True)

    additional_enquiry_officer_comments = models.TextField(max_length=2000, blank=True)

    # Document verifications with comments
    has_id_proof = models.BooleanField()
    id_proof_comments = models.TextField(max_length=1000, blank=True)

    has_age_proof = models.BooleanField()
    age_proof_comments = models.TextField(max_length=1000, blank=True)

    has_noc_from_landlord = models.BooleanField()
    noc_comments = models.TextField(max_length=1000, blank=True)

    has_ownership_proof = models.BooleanField()
    ownership_proof_comments = models.TextField(max_length=1000, blank=True)

    has_trade_license = models.BooleanField()
    trade_license_comments = models.TextField(max_length=1000, blank=True)

    proposes_barman_or_salesman = models.BooleanField()
    worker_proposal_comments = models.TextField(max_length=1000, blank=True)

    worker_docs_valid = models.BooleanField()
    worker_docs_comments = models.TextField(max_length=1000, blank=True)

    license_recommendation = models.BooleanField()
    recommendation_comments = models.TextField(max_length=1000, blank=True)

    special_remarks = models.TextField(max_length=2000, blank=True)
    reporting_place = models.CharField(max_length=250, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'site_enquiry_report'
        ordering = ['created_at']

    def __str__(self):
        return f"Site Enquiry Report for Application {self.application.application_id}"