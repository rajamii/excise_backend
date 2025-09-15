 # models.py
from django.db import models
from django.core.exceptions import ValidationError
from .validators import validate_name, validate_name_extended
from typing import TYPE_CHECKING
from .helper import ROAD_TYPE_CHOICES

if TYPE_CHECKING:
    # Type checking only imports to prevent circular imports
    from django.db.models.manager import Manager
    from .models import District, PoliceStation, Subdivision

class LicenseCategory(models.Model):
    license_category = models.CharField(
        max_length=200,
        null=False,
        blank=False,
        help_text="Name of license category"
    )

    class Meta:
        db_table = 'masters_licensecategory'
        verbose_name_plural = "License Categories"

    def __str__(self) -> str:
        return self.license_category

class LicenseType(models.Model):
    license_type = models.CharField(
        max_length=200,
        null=False,
        blank=False,
        help_text="Type of license"
    )

    class Meta:
        db_table = 'masters_licensetype'

    def __str__(self) -> str:
        return self.license_type

class State(models.Model):
    state = models.CharField(
        max_length=50,
        default='Sikkim',
        null=False,
        blank=False
    )
    state_code = models.IntegerField(
        unique=True,
        default=11
    )
    is_active = models.BooleanField(
        default=True
    )

    # Type hint for the reverse relationship from the District model
    if TYPE_CHECKING:
        districts: 'Manager[District]'

    class Meta:
        db_table = 'masters_state'
        constraints = [
            models.UniqueConstraint(
                fields=['state', 'state_code'],
                name='unique_state_identifier'
            )
        ]

    def __str__(self) -> str:
        return f"{self.state} ({self.state_code})"

    def clean(self):
        if not 10 <= self.state_code <= 99:
            raise ValidationError("State code must be between 10-99")

class District(models.Model):
    district = models.CharField(
        max_length=30,
        validators=[validate_name],
        null=False,
        blank=False
    )
    district_code = models.IntegerField(
        unique=True,
        default=225
    )
    is_active = models.BooleanField(
        default=True
    )
    state_code = models.ForeignKey(
        State,
        to_field='state_code',
        on_delete=models.CASCADE,
        related_name='districts',
        null=False,
        db_column='state_code'
    )

    # Type hint for the reverse relationship from the Subdivision model
    if TYPE_CHECKING:
        subdivisions: 'Manager[Subdivision]'

    class Meta:
        db_table = 'masters_district'
        constraints = [
            models.UniqueConstraint(
                fields=['state_code', 'district_code'],
                name='unique_district_code_per_state'
            )
        ]

    def __str__(self) -> str:
        return f"{self.district} ({self.district_code})"

class Subdivision(models.Model):
    subdivision = models.CharField(
        max_length=30,
        validators=[validate_name],
        null=True,
        blank=True
    )
    subdivision_code = models.IntegerField(
        unique=True,
        default=1553
    )
    is_active = models.BooleanField(
        default=True
    )
    district_code = models.ForeignKey(
        District,
        to_field='district_code',
        on_delete=models.CASCADE,
        related_name='subdivisions',
        null=True,
        db_column='district_code'
    )

    # Type hint for the reverse relationship from the PoliceStation model
    if TYPE_CHECKING:
        police_stations: 'Manager[PoliceStation]'

    class Meta:
        db_table = 'masters_subdivision'
        constraints = [
            models.UniqueConstraint(
                fields=['district_code', 'subdivision_code'],
                name='unique_subdivision_code_per_district'
            )
        ]

    def __str__(self) -> str:
        return f"{self.subdivision} ({self.subdivision_code})"

    def clean(self):
        if self.subdivision and len(self.subdivision.strip()) < 2:
            raise ValidationError("Subdivision name must be ≥2 characters")

    @property
    def active_police_stations(self) -> 'models.QuerySet[PoliceStation]':
        return self.police_stations.filter(is_active=True)

class PoliceStation(models.Model):
    police_station = models.CharField(
        max_length=30,
        validators=[validate_name],
        null=True,
        blank=True
    )
    police_station_code = models.IntegerField(
        unique=True,
        default=11999
    )
    is_active = models.BooleanField(
        default=True
    )
    subdivision_code = models.ForeignKey(
        Subdivision,
        to_field='subdivision_code',
        on_delete=models.CASCADE,
        related_name='police_stations',
        null=True,
        db_column='subdivision_code'
    )

    class Meta:
        db_table = 'masters_policestation'

    def __str__(self) -> str:
        return f"{self.police_station} ({self.police_station_code})"
    
# LicenseTitle
class LicenseTitle(models.Model):
    description = models.CharField(max_length=200, default=None, null=False)

    class Meta:
        db_table = 'masters_licensetitle'

    def __str__(self):
        return self.description

# LicenseSubcategory
class LicenseSubcategory(models.Model):
    description = models.CharField(max_length=200, default=None, null=False, validators=[validate_name_extended])
    category = models.ForeignKey(
        LicenseCategory,
        on_delete=models.CASCADE,
        related_name='subcategories',
    )

    class Meta:
        db_table = 'masters_licensesubcategory'

    def __str__(self):
        return self.description

# Location Road
class Road(models.Model):
    road_name = models.CharField(max_length=100, validators=[validate_name_extended])
    district = models.ForeignKey(
        District,
        to_field='district_code',
        on_delete=models.CASCADE,
        related_name='roads',
    )
    road_type = models.CharField(max_length=10, choices=ROAD_TYPE_CHOICES, default='NH')

    class Meta:
        db_table = 'masters_road'

    def __str__(self):
        return f"{self.road_name} ({self.road_type})"
