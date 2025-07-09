 # models.py
from django.db import models
from django.core.exceptions import ValidationError
from .validators import validate_name, validate_Numbers
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # Type checking only imports to prevent circular imports
    from django.db.models.manager import Manager
    from .models import District, PoliceStation, Subdivision

class LicenseCategory(models.Model):
    licenseCategoryDescription = models.CharField(
        max_length=200,
        null=False,
        blank=False,
        help_text="Description of license category"
    )

    class Meta:
        verbose_name_plural = "License Categories"

    def __str__(self) -> str:
        return self.licenseCategoryDescription

class LicenseType(models.Model):
    licenseType = models.CharField(
        max_length=200,
        null=False,
        blank=False,
        help_text="Type of license"
    )

    def __str__(self) -> str:
        return self.licenseType

class State(models.Model):
    State = models.CharField(
        max_length=50,
        default='Sikkim',
        null=False,
        blank=False
    )
    StateNameLL = models.CharField(
        max_length=30,
        validators=[validate_name],
        null=False,
        blank=False
    )
    StateCode = models.IntegerField(
        unique=True,
        default=11
    )
    IsActive = models.BooleanField(
        default=True
    )

    # Type hint for the reverse relationship from the District model
    if TYPE_CHECKING:
        districts: 'Manager[District]'

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['State', 'StateCode'],
                name='unique_state_identifier'
            )
        ]

    def __str__(self) -> str:
        return f"{self.State} ({self.StateCode})"

    def clean(self):
        if not 10 <= self.StateCode <= 99:
            raise ValidationError("State code must be between 10-99")

class District(models.Model):
    District = models.CharField(
        max_length=30,
        validators=[validate_name],
        null=False,
        blank=False
    )
    DistrictNameLL = models.CharField(
        max_length=30,
        validators=[validate_name],
        null=True,
        blank=True
    )
    DistrictCode = models.IntegerField(
        unique=True,
        default=117
    )
    IsActive = models.BooleanField(
        default=True
    )
    StateCode = models.ForeignKey(
        State,
        to_field='StateCode',
        on_delete=models.CASCADE,
        related_name='districts',
        null=False
    )

    # Type hint for the reverse relationship from the Subdivision model
    if TYPE_CHECKING:
        subdivisions: 'Manager[Subdivision]'

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['StateCode', 'DistrictCode'],
                name='unique_district_code_per_state'
            )
        ]

    def __str__(self) -> str:
        return f"{self.District} ({self.DistrictCode})"

class Subdivision(models.Model):
    SubDivisionName = models.CharField(
        max_length=30,
        validators=[validate_name],
        null=True,
        blank=True
    )
    SubDivisionNameLL = models.CharField(
        max_length=30,
        validators=[validate_name],
        null=True,
        blank=True
    )
    SubDivisionCode = models.IntegerField(
        unique=True,
        default=1001
    )
    IsActive = models.BooleanField(
        default=True
    )
    DistrictCode = models.ForeignKey(
        District,
        to_field='DistrictCode',
        on_delete=models.CASCADE,
        related_name='subdivisions',
        null=True
    )

    # Type hint for the reverse relationship from the PoliceStation model
    if TYPE_CHECKING:
        police_stations: 'Manager[PoliceStation]'

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['DistrictCode', 'SubDivisionCode'],
                name='unique_subdivision_code_per_district'
            )
        ]

    def __str__(self) -> str:
        return f"{self.SubDivisionName} ({self.SubDivisionCode})"

    def clean(self):
        if self.SubDivisionName and len(self.SubDivisionName.strip()) < 2:
            raise ValidationError("Subdivision name must be ≥2 characters")

    @property
    def active_police_stations(self) -> 'models.QuerySet[PoliceStation]':
        return self.police_stations.filter(IsActive=True)

class PoliceStation(models.Model):
    PoliceStationName = models.CharField(
        max_length=30,
        validators=[validate_name],
        null=True,
        blank=True
    )
    PoliceStationCode = models.IntegerField(
        unique=True,
        default=11999
    )
    IsActive = models.BooleanField(
        default=True
    )
    SubDivisionCode = models.ForeignKey(
        Subdivision,
        to_field='SubDivisionCode',
        on_delete=models.CASCADE,
        related_name='police_stations',
        null=True
    )

    def __str__(self) -> str:
        return f"{self.PoliceStationName} ({self.PoliceStationCode})"
