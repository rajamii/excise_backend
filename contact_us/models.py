from django.db import models

class NodalOfficer(models.Model):
    department = models.CharField(max_length=255, default="Excise Department")
    cell = models.CharField(max_length=255, default="IT Cell")
    phone_number = models.CharField(max_length=20, default="(035) 9220-3963")
    email = models.EmailField(default="helpdesk-excise@sikkim.gov.in")

    def __str__(self):
        return f"Nodal Officer - {self.department}"

    def get_contact_details(self):
        return f"{self.phone_number}, {self.email}"

class Official(models.Model):
    name = models.CharField(max_length=255)
    designation = models.CharField(max_length=255)
    phone_number = models.CharField(max_length=20)
    email = models.EmailField()

    class Meta:
        abstract = True  # This is an abstract class, so it won't be used directly in the database

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
    )
    
    # Fields for headquarter information
    officer_name_headquarter = models.CharField(max_length=255, null=True, blank=True)
    designation_headquarter = models.CharField(max_length=255, null=True, blank=True)
    address_headquarter = models.TextField(null=True, blank=True)
    phone_number_headquarter = models.CharField(max_length=20, null=True, blank=True)

    # Fields for district information
    district = models.CharField(max_length=255, null=True, blank=True)
    officer_name_district = models.CharField(max_length=255, null=True, blank=True)
    designation_district = models.CharField(max_length=255, null=True, blank=True)
    address_district = models.TextField(null=True, blank=True)
    phone_number_district = models.CharField(max_length=20, null=True, blank=True)

    def __str__(self):
        return f"Public Information Officer - {self.location}"

    def is_headquarter(self):
        return self.location == self.HEADQUARTER

    def is_district(self):
        return self.location == self.DISTRICT

class DirectorateAndDistrictOfficials(Official):
    pass  # Inherits all fields from Official

class GrievanceRedressalOfficer(Official):
    OFFICE_LEVEL_CHOICES = [
        ('Head Quarter', 'Head Quarter'),
        ('Permit Section', 'Permit Section'),
        ('Administration Section', 'Administration Section'), 
        ('Accounts Section', 'Accounts Section'),
        ('IT Cell', 'IT Cell'),  # Option for any other office level
    ]

    # Define fields for the Grievance Redressal Officer
    office_level = models.CharField(
        max_length=255, 
        choices=OFFICE_LEVEL_CHOICES, 
        default='Excise Head Office'
    )
    office_sub_level = models.CharField(max_length=255, null=True, blank=True)

    def __str__(self):
        return f"Grievance Redressal Officer - {self.name}, {self.office_level}"
