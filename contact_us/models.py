from django.db import models

from .validators import (
    validate_phone_number,
    validate_email,
    validate_department_name,
    validate_designation,
    validate_non_empty,
    validate_location,
    validate_office_level
)

'''
    Model: NodalOfficer
    Stores contact info for a main department contact
'''

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
    phoneNumber = models.CharField(
        max_length=20, 
        default="(035) 9220-3963", 
        validators=[validate_phone_number], 
        db_column='phone_number'  
    )
    email = models.EmailField(
        default="helpdesk-excise@sikkim.gov.in", 
        validators=[validate_email]  
    )

    def __str__(self):
        return f"Nodal Officer - {self.department}"

    def get_contact_details(self):
        return f"{self.phone_number}, {self.email}"

'''
    Abstract Model: Official
    Base class for all officer types
'''

class Official(models.Model):
    name = models.CharField(
        max_length=255, 
        validators=[validate_non_empty]
    )
    designation = models.CharField(
        max_length=255, 
        validators=[validate_designation]
    )
    phoneNumber = models.CharField(
        max_length=20, 
        validators=[validate_phone_number],
        db_column='phone_number',
        default='00000000000'
    )
    email = models.EmailField(
        validators=[validate_email]
    )

    class Meta:
        abstract = True  # Not a table ; used for inheritance

    def __str__(self):
        return f"{self.name} - {self.designation}"
'''
    Model: PublicInformationOfficer
    Inherits from Official; adds location-related fields   
'''

class PublicInformationOfficer(Official):
    HEADQUARTER = 'Headquarter'
    DISTRICT    = 'District'
    UNSET       = 'unset'

    LOCATION_TYPE_CHOICES = [
        (HEADQUARTER, 'Headquarter'),
        (DISTRICT, 'District'),
        (UNSET , 'unset'),
    ]

    locationType = models.CharField(
        max_length=20,
        choices=LOCATION_TYPE_CHOICES,
        db_column='location_type',
        default=UNSET,
    )
    location = models.CharField(max_length=100)  # Specific location name
    address = models.CharField(max_length=255, default='Not Available')  # Full address

    def __str__(self):
        return f"{self.name} ({self.designation}) - {self.location}"

    def is_headquarter(self):
        return self.location == self.HEADQUARTER

    def is_district(self):
        return self.location == self.DISTRICT

# Model: DirectorateAndDistrictOfficials
# Basic model for officials at both levels
class DirectorateAndDistrictOfficials(models.Model):
    name = models.CharField(max_length=255)
    designation = models.CharField(max_length=255)
    phoneNumber = models.CharField(
        max_length=20, 
        blank=True, 
        null=True, 
        db_column='phone_number'
    )
    email = models.EmailField(
        validators=[validate_email], 
        blank=True, 
        null=True
    )

    def __str__(self):
        return f"{self.name} - {self.designation}"

# Model: GrievanceRedressalOfficer
# Inherits from Official; adds office level info
class GrievanceRedressalOfficer(Official):

    OFFICE_LEVEL_CHOICES = [
        ('Head Quarter', 'Head Quarter'),
        ('Permit Section', 'Permit Section'),
        ('Administration Section', 'Administration Section'), 
        ('Accounts Section', 'Accounts Section'),
        ('IT Cell', 'IT Cell'),
    ]

    officeLevel = models.CharField(
        max_length=255, 
        choices=OFFICE_LEVEL_CHOICES, 
        default='Excise Head Office',
        validators=[validate_office_level],
        db_column='office_level'
    )
    officeSubLevel = models.CharField(
        max_length=255, 
        null=True, 
        blank=True,
        validators=[validate_non_empty],
        db_column='office_sub_level'
    )

    def __str__(self):
        return f"Grievance Redressal Officer - {self.name}, {self.office_level}"
