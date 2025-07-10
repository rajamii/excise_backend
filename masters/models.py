from django.db import models
from .validators import validate_name, validate_name_extended
from .helper import ROAD_TYPE_CHOICES

# State
class State(models.Model):
    state = models.CharField(max_length=30, validators=[validate_name])
    state_code = models.IntegerField(unique=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.state

# District
class District(models.Model):
    district = models.CharField(max_length=30, validators=[validate_name])
    district_code = models.IntegerField(unique=True)
    is_active = models.BooleanField(default=True)
    state_code = models.ForeignKey(
        State, to_field='state_code',
        on_delete=models.CASCADE,
        related_name='districts',
        )

    def __str__(self):
        return self.district

# Subdivision
class Subdivision(models.Model):
    subdivision = models.CharField(max_length=30, validators=[validate_name])
    subdivision_code = models.IntegerField(unique=True)
    is_active = models.BooleanField(default=True)
    district_code = models.ForeignKey(
        District, to_field='district_code',
        on_delete=models.CASCADE,
        related_name='subdivisions',
        )

    def __str__(self):
        return self.subdivision

# PoliceStation
class PoliceStation(models.Model):
    police_station = models.CharField(max_length=30, validators=[validate_name])
    police_station_code = models.IntegerField(unique=True)
    is_active = models.BooleanField(default=True)
    subdivision_code = models.ForeignKey(
        Subdivision, to_field='subdivision_code',
        on_delete=models.CASCADE,
        related_name='policestations',
        )
    def __str__(self):
        return self.police_station

# LicenseCategory
class LicenseCategory(models.Model):
    license_category = models.CharField(max_length=200, default=None, null=False)

    def __str__(self):
        return self.license_category

# LicenseType
class LicenseType(models.Model):
    license_type = models.CharField(max_length=200, default=None, null=False)

    def __str__(self):
        return self.license_type

# LicenseTitle
class LicenseTitle(models.Model):
    description = models.CharField(max_length=200, default=None, null=False)

    def __str__(self):
        return self.description

# LicenseSubcategory
class LicenseSubcategory(models.Model):
    description = models.CharField(max_length=200, default=None, null=False, validators=[validate_name_extended])
    category = models.ForeignKey(
        LicenseCategory,
        on_delete=models.CASCADE,
        related_name='subcategories',
        db_column='license_category_id'
    )

    def __str__(self):
        return self.description

# Location Road
class Road(models.Model):
    road_name = models.CharField(max_length=100, validators=[validate_name_extended])
    district_id = models.ForeignKey(
        District,
        to_field='district_code',
        on_delete=models.CASCADE,
        related_name='roads',
        db_column='district_id'
    )
    road_type = models.CharField(max_length=10, choices=ROAD_TYPE_CHOICES, default='NH')

    def __str__(self):
        return f"{self.road_name} ({self.road_type})"