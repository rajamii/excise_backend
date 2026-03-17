from django.db import models
from django.core.exceptions import ValidationError
from .validators import validate_name, validate_name_extended
# models.py
from typing import TYPE_CHECKING

from django.core.exceptions import ValidationError
from django.db import models

from .helper import ROAD_TYPE_CHOICES
from .validators import validate_name, validate_name_extended

if TYPE_CHECKING:
    from django.db.models.manager import Manager



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
    district_code = models.IntegerField(unique=True, default=225)
    is_active = models.BooleanField(default=True)
    state_code = models.ForeignKey(
        State,
        to_field='state_code',
        on_delete=models.CASCADE,
        related_name='districts',
        null=False,
        db_column='state_code'
    )

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
    subdivision_code = models.IntegerField(unique=True, default=1553)
    is_active = models.BooleanField(default=True)
    district_code = models.ForeignKey(
        District,
        to_field='district_code',
        on_delete=models.CASCADE,
        related_name='subdivisions',
        null=True,
        db_column='district_code'
    )

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
            raise ValidationError("Subdivision name must be >=2 characters")

    @property
    def active_police_stations(self):
        return self.police_stations.filter(is_active=True)


class PoliceStation(models.Model):
    police_station = models.CharField(
        max_length=30,
        validators=[validate_name],
        null=True,
        blank=True
    )
    police_station_code = models.IntegerField(unique=True, default=11999)
    is_active = models.BooleanField(default=True)
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


class LicenseTitle(models.Model):
    description = models.CharField(max_length=200, default=None, null=False)

    class Meta:
        db_table = 'masters_licensetitle'

    def __str__(self):
        return self.description


class LicenseSubcategory(models.Model):
    description = models.CharField(
        max_length=200,
        default=None,
        null=False,
        validators=[validate_name_extended]
    )
    category = models.ForeignKey(
        LicenseCategory,
        on_delete=models.CASCADE,
        related_name='subcategories',
    )

    class Meta:
        db_table = 'masters_licensesubcategory'

    def __str__(self):
        return self.description


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


# ─────────────────────────────────────────────────────────────────────────────
# Location models
# ─────────────────────────────────────────────────────────────────────────────

class LocationCategory(models.Model):
    category_name = models.CharField(
        max_length=100,
        unique=True,
        null=False,
        blank=False,
        validators=[validate_name_extended],
        help_text="Name of the location category"
    )
    description = models.TextField(null=True, blank=True, help_text="Detailed description")
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        'user.CustomUser',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_location_categories'
    )
    operation_date = models.DateTimeField(auto_now_add=True)
class LocationFee(models.Model):
    location_name = models.CharField(max_length=100, unique=True)
    fee_amount = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        db_table = 'masters_locationcategory'
        verbose_name = 'Location Category'
        verbose_name_plural = 'Location Categories'
       

    def __str__(self) -> str:
        return self.category_name


class LocationSubcategory(models.Model):
    subcategory_name = models.CharField(
        max_length=100,
        null=False,
        blank=False,
        validators=[validate_name_extended],
        help_text="Name of the location subcategory"
    )
    category = models.ForeignKey(
        LocationCategory,
        on_delete=models.CASCADE,
        related_name='subcategories',
        null=False
    )
    description = models.TextField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        'user.CustomUser',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_location_subcategories'
    )
    operation_date = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'masters_locationsubcategory'
        verbose_name = 'Location Subcategory'
        verbose_name_plural = 'Location Subcategories'
        constraints = [
            models.UniqueConstraint(
                fields=['category', 'subcategory_name'],
                name='unique_subcategory_per_category'
            )
        ]
        ordering = ['category', 'subcategory_name']

    def __str__(self) -> str:
        return f"{self.subcategory_name} ({self.category.category_name})"


class Location(models.Model):
    location_code = models.IntegerField(
        unique=True,
        null=False,
        blank=False,
        help_text="Unique location code"
    )
    location_description = models.CharField(
        max_length=200,
        null=False,
        blank=False,
        help_text="Description of the location"
    )
    district_code = models.ForeignKey(
        District,
        to_field='district_code',
        on_delete=models.CASCADE,
        related_name='locations',
        null=False,
        db_column='district_code'
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'masters_location'
        constraints = [
            models.UniqueConstraint(
                fields=['district_code', 'location_code'],
                name='unique_location_code_per_district'
            )
        ]

    def __str__(self) -> str:
        return f"{self.location_description} ({self.location_code})"

    def clean(self):
        if self.location_description:
            validate_name_extended(self.location_description)
            if len(self.location_description.strip()) < 2:
                raise ValidationError("Location description must be ≥2 characters")


class Ward(models.Model):
    ward_name = models.CharField(
        max_length=100,
        null=False,
        blank=False,
        validators=[validate_name_extended]
    )
    ward_number = models.IntegerField(null=False, blank=False)
    location_code = models.ForeignKey(
        Location,
        to_field='location_code',
        on_delete=models.CASCADE,
        related_name='wards',
        null=False,
        db_column='location_code'
    )
    population = models.IntegerField(null=True, blank=True)
    area_sq_km = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        'user.CustomUser',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_wards'
    )
    operation_date = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'masters_ward'
        verbose_name = 'Ward'
        verbose_name_plural = 'Wards'
        constraints = [
            models.UniqueConstraint(
                fields=['location_code', 'ward_number'],
                name='unique_ward_number_per_location'
            )
        ]
        ordering = ['location_code', 'ward_number']

    def __str__(self) -> str:
        return f"Ward {self.ward_number} - {self.ward_name}"

    def clean(self):
        if self.ward_number <= 0:
            raise ValidationError("Ward number must be positive")
        if self.population is not None and self.population < 0:
            raise ValidationError("Population cannot be negative")
        if self.area_sq_km is not None and self.area_sq_km <= 0:
            raise ValidationError("Area must be positive")


# ─────────────────────────────────────────────────────────────────────────────
# License Fee
# ─────────────────────────────────────────────────────────────────────────────

class LicenseFee(models.Model):
    license_category = models.ForeignKey(
        LicenseCategory,
        on_delete=models.CASCADE,
        related_name='license_fees',
        null=False
    )
    license_subcategory = models.ForeignKey(
        LicenseSubcategory,
        on_delete=models.CASCADE,
        related_name='license_fees',
        null=False
    )
    location_code = models.ForeignKey(
        Location,
        to_field='location_code',
        on_delete=models.CASCADE,
        related_name='license_fees',
        null=False,
        db_column='location_code'
    )
    license_fee = models.DecimalField(max_digits=10, decimal_places=2)
    security_amount = models.DecimalField(max_digits=10, decimal_places=2)
    renewal_amount = models.DecimalField(max_digits=10, decimal_places=2)
    late_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        'user.CustomUser',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_license_fees'
    )
    operation_date = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'license_fee'
        constraints = [
            models.UniqueConstraint(
                fields=['license_category', 'license_subcategory', 'location_code'],
                name='unique_license_fee_combination'
            )
        ]

    def __str__(self):
        return f"{self.location_name} - Rs {self.fee_amount}"


class SupplyChainTimerConfig(models.Model):
    TIMER_UNIT_SECOND = 'second'
    TIMER_UNIT_MINUTE = 'minute'
    TIMER_UNIT_HOUR = 'hour'
    TIMER_UNIT_DAY = 'day'

    TIMER_UNIT_CHOICES = [
        (TIMER_UNIT_SECOND, 'Second'),
        (TIMER_UNIT_MINUTE, 'Minute'),
        (TIMER_UNIT_HOUR, 'Hour'),
        (TIMER_UNIT_DAY, 'Day'),
    ]

    code = models.CharField(max_length=100, unique=True)
    description = models.CharField(max_length=255, blank=True)
    delay_value = models.PositiveIntegerField(default=10)
    delay_unit = models.CharField(max_length=10, choices=TIMER_UNIT_CHOICES, default=TIMER_UNIT_SECOND)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'timer'
        verbose_name = 'Supply Chain Timer Config'
        verbose_name_plural = 'Supply Chain Timer Configs'

    def __str__(self):
        return f"{self.code}: {self.delay_value} {self.delay_unit}(s)"
