from django.db import models, transaction
from django.contrib.contenttypes.fields import GenericRelation
from django.utils.timezone import now
from . import helpers
from models.masters.core.models import District, Subdivision, PoliceStation, LicenseCategory, LicenseSubcategory, LicenseType
from auth.user.models import CustomUser
from auth.workflow.models import Workflow, WorkflowStage, Transaction, Objection

def upload_document_path(instance, filename):
    return f'new_license_application/{instance.application_id}/{filename}'


class NewLicenseApplication(models.Model):
    application_id = models.CharField(max_length=30, primary_key=True, db_index=True)
    workflow = models.ForeignKey(Workflow, on_delete=models.PROTECT, related_name='new_license_applications')
    current_stage = models.ForeignKey(WorkflowStage, on_delete=models.PROTECT, related_name='new_license_applications')

    # System flags
    is_approved = models.BooleanField(default=False)
    print_count = models.PositiveIntegerField(default=0)
    is_print_fee_paid = models.BooleanField(default=False)
    is_fee_calculated = models.BooleanField(default=False) #For Level 1
    is_license_fee_paid = models.BooleanField(default=False)
    is_license_category_updated = models.BooleanField(default=False) # For Level 2
    
    yearly_license_fee = models.CharField(max_length=100, blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # === Application Type ===
    license_type = models.ForeignKey(LicenseType, on_delete=models.PROTECT)

    # === Basic Information ===
    license_category = models.ForeignKey(LicenseCategory, on_delete=models.PROTECT)
    license_sub_category = models.ForeignKey(LicenseSubcategory, on_delete=models.PROTECT)
    establishment_name = models.CharField(max_length=150)
    site_type = models.CharField(max_length=10, choices=[('New', 'New'), ('Existing', 'Existing')])

    # === Applicant Details ===
    applicant_name = models.CharField(max_length=150)
    father_husband_name = models.CharField(max_length=150)
    dob = models.DateField()
    gender = models.CharField(max_length=10, choices=[('Male', 'Male'), ('Female', 'Female')])
    nationality = models.CharField(max_length=50)
    residential_status = models.CharField(max_length=20, choices=[('Resident', 'Resident'), ('Non-Resident', 'Non-Resident')])
    present_address = models.TextField()
    permanent_address = models.TextField()
    pan = models.CharField(max_length=10)
    email = models.EmailField()
    mobile_number = models.CharField(max_length=10)
    mode_of_operation = models.CharField(max_length=20, choices=[('Self', 'Self'), ('Salesman', 'Salesman'), ('Barman', 'Barman')])
    has_sikkim_certificate = models.CharField(max_length=3, choices=[('Yes', 'Yes'), ('No', 'No')])
    has_excise_license = models.CharField(max_length=3, choices=[('Yes', 'Yes'), ('No', 'No')])
    family_excise_license = models.CharField(max_length=3, choices=[('Yes', 'Yes'), ('No', 'No')])
    criminal_conviction = models.CharField(max_length=3, choices=[('Yes', 'Yes'), ('No', 'No')])

    # === Site Details ===
    site_district = models.ForeignKey(District, on_delete=models.PROTECT, related_name='new_license_site_districts')
    site_subdivision = models.ForeignKey(Subdivision, on_delete=models.PROTECT, related_name='new_license_site_subdivisions')
    police_station = models.ForeignKey(PoliceStation, on_delete=models.PROTECT)
    location_category = models.CharField(max_length=100)
    location_name = models.CharField(max_length=100)
    ward_name = models.CharField(max_length=100)
    business_address = models.TextField()
    road_name = models.CharField(max_length=100)
    pin_code = models.CharField(max_length=6)
    construction_type = models.CharField(max_length=50)
    length = models.DecimalField(max_digits=6, decimal_places=2, blank=True, null=True)
    breadth = models.DecimalField(max_digits=6, decimal_places=2, blank=True, null=True)
    site_owned = models.CharField(max_length=3, choices=[('Yes', 'Yes'), ('No', 'No')])
    noc_obtained = models.CharField(max_length=3, choices=[('Yes', 'Yes'), ('No', 'No')])

    # === Company Details (Conditional) ===
    company_name = models.CharField(max_length=255, blank=True, null=True)
    company_address = models.TextField(blank=True, null=True)
    company_pan = models.CharField(max_length=10, blank=True, null=True)
    company_cin = models.CharField(max_length=21, blank=True, null=True)
    incorporation_date = models.DateField(blank=True, null=True)
    company_phone_number = models.CharField(max_length=10, blank=True, null=True)
    company_email = models.EmailField(blank=True, null=True)

    # === Documents ===
    pass_photo = models.FileField(upload_to=upload_document_path)
    pan_card = models.FileField(upload_to=upload_document_path)
    sikkim_certificate = models.FileField(upload_to=upload_document_path)
    dob_proof = models.FileField(upload_to=upload_document_path)
    noc_landlord = models.FileField(upload_to=upload_document_path, blank=True, null=True)

    applicant = models.ForeignKey(
        CustomUser,
        on_delete=models.PROTECT,
        related_name='license_applications'
    )

    # Polymorphic links
    transactions = GenericRelation(
        Transaction,
        content_type_field='content_type',
        object_id_field='object_id',
        related_query_name='new_license_application'
    )
    objections = GenericRelation(
        Objection,
        content_type_field='content_type',
        object_id_field='object_id',
        related_query_name='new_license_application'
    )

    def record_license_print(self, fee_paid=False):
        self.print_count += 1
        if self.print_count > 5 and fee_paid:
            self.is_print_fee_paid = True
        self.save()
    
    def can_print_license(self):
        if self.print_count < 5:
            return True, 0  # Allowed to print, no fee required
        elif self.is_print_fee_paid:
            return True, 500  # Allowed to print, fee has been paid
        else:
            return False, 500  # Not allowed, fee required
        
    def clean(self):
        if self.license_type:
            helpers.validate_license_type(self.license_type)
        helpers.validate_mobile_number(self.mobile_number)
        if self.company_phone_number is not None:
            helpers.validate_mobile_number(self.company_phone_number)
        

        helpers.validate_email_field(self.email)
        if self.company_email:
            helpers.validate_email_field(self.company_email)
        

        if self.company_pan:
            helpers.validate_pan_number(self.company_pan)
        helpers.validate_pan_number(self.pan)
        if self.company_cin:
            helpers.validate_cin_number(self.company_cin)

        
        helpers.validate_gender(self.gender)
        helpers.validate_pin_code(self.pin_code)

    def save(self, *args, **kwargs):
        if not self.application_id:
            self.application_id = self.generate_application_id()
        super().save(*args, **kwargs)

    def generate_application_id(self):
        try:
            district_code = str(self.site_district.district_code).strip()
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
            last_app = NewLicenseApplication.objects.filter(
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

            return f"NLI/{prefix}/{new_number_str}"
        
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
        db_table = 'new_license_application'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['site_district']),
            models.Index(fields=['license_type']),
            models.Index(fields=['site_subdivision']),
            models.Index(fields=['current_stage']),
            models.Index(fields=['applicant']),
        ]