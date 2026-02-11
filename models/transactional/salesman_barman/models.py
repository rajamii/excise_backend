from django.db import models, transaction
from django.contrib.contenttypes.fields import GenericRelation
from django.core.exceptions import ValidationError
from django.utils.timezone import now
from auth.roles.models import Role
from auth.user.models import CustomUser
from models.masters.license.models import License
from models.masters.core.models import District, LicenseCategory
from auth.workflow.models import Workflow, WorkflowStage, Transaction, Objection
from .helpers import (
    validate_pan_number, validate_aadhaar_number, validate_phone_number,
    validate_address, validate_email, ROLE_CHOICES, GENDER_CHOICES
)

def upload_document_path(instance, filename):
    return f'salesman_barman/{instance.application_id}/{filename}'

class SalesmanBarmanModel(models.Model):
    application_id = models.CharField(max_length=30, primary_key=True, db_index=True)
    workflow = models.ForeignKey(Workflow, on_delete=models.PROTECT, related_name='salesman_barman_applications')
    current_stage = models.ForeignKey(WorkflowStage, on_delete=models.PROTECT, related_name='salesman_barman_applications')
    
    is_approved = models.BooleanField(default=False)
    print_count = models.PositiveIntegerField(default=0)
    is_print_fee_paid = models.BooleanField(default=False)

    # --- License Details ---
    excise_district = models.ForeignKey(District, on_delete=models.PROTECT)
    license_category = models.ForeignKey(LicenseCategory, on_delete=models.PROTECT)
    license = models.ForeignKey(License, on_delete=models.PROTECT)

    # --- Personal ---
    role = models.CharField(max_length=10, choices=ROLE_CHOICES)
    firstName = models.CharField(max_length=100, db_column='first_name')
    middleName = models.CharField(max_length=100, blank=True, null=True, db_column='middle_name')
    lastName = models.CharField(max_length=100, db_column='last_name')
    fatherHusbandName = models.CharField(max_length=100, db_column='father_husband_name')
    gender = models.CharField(max_length=6, choices=GENDER_CHOICES)
    dob = models.DateField()
    nationality = models.CharField(max_length=50, default='Indian')
    address = models.TextField(validators=[validate_address])

    # --- Identity ---
    pan = models.CharField(max_length=10, validators=[validate_pan_number])
    aadhaar = models.CharField(max_length=12, validators=[validate_aadhaar_number])
    mobileNumber = models.CharField(max_length=10, validators=[validate_phone_number], db_column='mobile_number')
    emailId = models.EmailField(blank=True, validators=[validate_email], db_column='email_id')
    sikkimSubject = models.BooleanField(default=False, db_column='sikkim_subject')

    # --- Documents ---
    passPhoto = models.ImageField(upload_to=upload_document_path, db_column='pass_photo')
    aadhaarCard = models.FileField(upload_to=upload_document_path, db_column='aadhaar_card')
    residentialCertificate = models.FileField(upload_to=upload_document_path, db_column='residential_certificate')
    dateofBirthProof = models.FileField(upload_to=upload_document_path, db_column='dateof_birth_proof')

    # --- Soft Delete ---
    # IsActive = models.BooleanField(default=True, db_column='is_active')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    applicant = models.ForeignKey(
        CustomUser,
        on_delete=models.PROTECT,
        null=True, blank=True,
        related_name='salesman_barman_applications'
    )

    renewal_of = models.ForeignKey(
        License,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='salesman_barman_renewal'
    )

     # Polymorphic links
    transactions = GenericRelation(
        Transaction,
        content_type_field='content_type',
        object_id_field='object_id',
        related_query_name='salesman_barman'
    )
    objections = GenericRelation(
        Objection,
        content_type_field='content_type',
        object_id_field='object_id',
        related_query_name='salesman_barman'
    )

    def __str__(self):
        return f"{self.role}: {self.firstName} {self.lastName} ({self.application_id})"

    def clean(self):
        if self.dob >= now().date():
            raise ValidationError("Date of birth cannot be in the future.")
        
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
            last_app = SalesmanBarmanModel.objects.filter(
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

            return f"SBM/{prefix}/{new_number_str}"
        
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
        db_table = 'salesman_barman_application'
        indexes = [
            models.Index(fields=['excise_district']),
            models.Index(fields=['license_category']),
            models.Index(fields=['current_stage']),
            models.Index(fields=['applicant']),
        ]