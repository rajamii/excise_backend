from django.db import models
from .validators import validate_phone_number, validate_email, validate_department_name, validate_designation, validate_non_empty, validate_location, validate_office_level

class NodalOfficer(models.Model):
    department = models.CharField(
        max_length=255, 
        default="Excise Department", 
        validators=[validate_department_name]
    )
    cell = models.CharField(
        max_length=255, 
        default="IT Cell", 
        validators=[validate_non_empty]
    )
    phone_number = models.CharField(
        max_length=20, 
        default="(035) 9220-3963", 
        validators=[validate_phone_number]
    )
    email = models.EmailField(
        default="helpdesk-excise@sikkim.gov.in", 
        validators=[validate_email]
    )

    def __str__(self):
        return f"Nodal Officer - {self.department}"

    def get_contact_details(self):
        return f"{self.phone_number}, {self.email}"

class Official(models.Model):
    name = models.CharField(
        max_length=255, 
        validators=[validate_non_empty]
    )
    designation = models.CharField(
        max_length=255, 
        validators=[validate_designation]
    )
    phone_number = models.CharField(
        max_length=20, 
        validators=[validate_phone_number]
    )
    email = models.EmailField(
        validators=[validate_email]
    )

    class Meta:
        abstract = True

    def __str__(self):
        return f"{self.name} - {self.designation}"

class PublicInformationOfficer(Official):
    HEADQUARTER = 'HQ'
    DISTRICT = 'District'

    LOCATION_CHOICES = [
        (HEADQUARTER, 'Headquarter'),
        (DISTRICT, 'District'),
    ]

    location = models.CharField(
        max_length=10,
        choices=LOCATION_CHOICES,
        default=HEADQUARTER,
        validators=[validate_location]
    )
    
    officer_name_headquarter = models.CharField(
        max_length=255, 
        null=True, 
        blank=True, 
        validators=[validate_non_empty]
    )
    designation_headquarter = models.CharField(
        max_length=255, 
        null=True, 
        blank=True, 
        validators=[validate_designation]
    )
    address_headquarter = models.TextField(
        null=True, 
        blank=True, 
        validators=[validate_non_empty]
    )
    phone_number_headquarter = models.CharField(
        max_length=20, 
        null=True, 
        blank=True, 
        validators=[validate_phone_number]
    )

    district = models.CharField(
        max_length=255, 
        null=True, 
        blank=True, 
        validators=[validate_non_empty]
    )
    officer_name_district = models.CharField(
        max_length=255, 
        null=True, 
        blank=True, 
        validators=[validate_non_empty]
    )
    designation_district = models.CharField(
        max_length=255, 
        null=True, 
        blank=True, 
        validators=[validate_designation]
    )
    address_district = models.TextField(
        null=True, 
        blank=True, 
        validators=[validate_non_empty]
    )
    phone_number_district = models.CharField(
        max_length=20, 
        null=True, 
        blank=True, 
        validators=[validate_phone_number]
    )

    def __str__(self):
        return f"Public Information Officer - {self.location}"

    def is_headquarter(self):
        return self.location == self.HEADQUARTER

    def is_district(self):
        return self.location == self.DISTRICT

class DirectorateAndDistrictOfficials(Official):
    pass

class GrievanceRedressalOfficer(Official):
    OFFICE_LEVEL_CHOICES = [
        ('Head Quarter', 'Head Quarter'),
        ('Permit Section', 'Permit Section'),
        ('Administration Section', 'Administration Section'), 
        ('Accounts Section', 'Accounts Section'),
        ('IT Cell', 'IT Cell'),
    ]

    office_level = models.CharField(
        max_length=255, 
        choices=OFFICE_LEVEL_CHOICES, 
        default='Excise Head Office',
        validators=[validate_office_level]
    )
    office_sub_level = models.CharField(
        max_length=255, 
        null=True, 
        blank=True,
        validators=[validate_non_empty]
    )

    def __str__(self):
        return f"Grievance Redressal Officer - {self.name}, {self.office_level}"
