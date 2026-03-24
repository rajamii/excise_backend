from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager
from django.core.validators import validate_email
from django.conf import settings
from auth.user.validators import validate_name, validate_phone_number
from auth.roles.models import Role
from models.masters.core.models import District, Subdivision
from models.masters.core.helper import GENDER_CHOICES, MARITAL_STATUS_CHOICES, RESIDENTIAL_STATUS_CHOICES
from django.utils import timezone
import uuid
import random


class CustomUserManager(BaseUserManager):
    def create_user(self, email, first_name, last_name, phone_number,
                   district, subdivision, address, password=None, **extra_fields):
        """
        Creates and saves a User with the given required fields.
        """
        if not email:
            raise ValueError('The Email must be set')
        if not first_name:
            raise ValueError('First name must be set')
        if not last_name:
            raise ValueError('Last name must be set')
        if not phone_number:
            raise ValueError('Phone number must be set')

        email = self.normalize_email(email)
        username = self.generate_unique_username(
            first_name=first_name,
            last_name=last_name,
            phone_number=phone_number,
            district=district,
            subdivision=subdivision
        )

        user = self.model(
            email=email,
            username=username,
            first_name=first_name,
            last_name=last_name,
            phone_number=phone_number,
            district=district,
            subdivision=subdivision,
            address=address,
            **extra_fields
        )
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, username, first_name, last_name, phone_number,
                         password=None, **extra_fields):
        """
        Creates and saves a superuser with the given required fields.
        """
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')

        email = extra_fields.pop('email', None) or f'{username}@example.com'
        address = extra_fields.pop('address', None) or 'Admin Office'
        district = extra_fields.pop('district', None) or District.objects.first()
        subdivision = extra_fields.pop('subdivision', None) or Subdivision.objects.first()

        if not district or not subdivision:
            raise ValueError('District and Subdivision are required. Please create master data first.')

        user = self.create_user(
            email=email,
            first_name=first_name,
            last_name=last_name,
            phone_number=phone_number,
            district=district,
            subdivision=subdivision,
            address=address,
            password=password,
            **extra_fields
        )

        user.username = username
        user.save(using=self._db)
        return user

    def generate_unique_username(self, first_name, last_name, phone_number, district, subdivision):
        initials = f"{first_name[0].upper()}{last_name[0].upper()}"
        district_code = district.district_code
        subdivision_code = subdivision.subdivision_code
        base = f"{initials}{phone_number[-4:]}{district_code}{subdivision_code}"
        username = base[:10]

        while self.model.objects.filter(username=username).exists():
            username = f"{base[:7]}{random.randint(100, 999)}"
        return username


class CustomUser(AbstractBaseUser):
    email = models.EmailField(
        unique=True,
        validators=[validate_email],
        error_messages={'unique': "A user with that email already exists."}
    )
    username = models.CharField(
        max_length=30,
        unique=True,
        blank=True  # Auto-generated
    )
    first_name = models.CharField(
        max_length=50,
        validators=[validate_name],
        error_messages={'blank': "First name cannot be blank."}
    )
    middle_name = models.CharField(
        max_length=50,
        validators=[validate_name],
        blank=True
    )
    last_name = models.CharField(
        max_length=50,
        validators=[validate_name],
        error_messages={'blank': "Last name cannot be blank."}
    )
    phone_number = models.CharField(
        max_length=10,
        unique=True,
        validators=[validate_phone_number],
        error_messages={'unique': "A user with that phone number already exists."}
    )
    district = models.ForeignKey(
        District,
        to_field='district_code',
        on_delete=models.CASCADE,
        db_column='district'
    )
    subdivision = models.ForeignKey(
        Subdivision,
        to_field='subdivision_code',
        on_delete=models.CASCADE,
        db_column='subdivision'
    )
    address = models.CharField(max_length=70, blank=True, null=True)
    role = models.ForeignKey(
        Role,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='users'
    )
    is_superuser = models.BooleanField(default=False)
    is_staff = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    date_joined = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        'self',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='created_users'
    )
    is_oic_managed = models.BooleanField(default=False)

    objects = CustomUserManager()

    USERNAME_FIELD = 'username'
    REQUIRED_FIELDS = ['first_name', 'last_name', 'phone_number']

    class Meta:
        db_table = 'custom_user'
        verbose_name = 'user'
        verbose_name_plural = 'users'
        ordering = ['-date_joined']

    def __str__(self):
        return self.username or self.email

    def clean(self):
        super().clean()
        self.email = self.__class__.normalize_email(self.email)


class OTP(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    phone_number = models.CharField(max_length=15)
    otp = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    used = models.BooleanField(default=False)

    def is_expired(self):
        return (timezone.now() - self.created_at).total_seconds() > 600  # 10 minutes

    @staticmethod
    def clean_expired_otps():
        OTP.objects.filter(
            used=False,
            created_at__lt=timezone.now() - timezone.timedelta(minutes=10)
        ).delete()

    def __str__(self):
        return f"{self.phone_number} - {self.otp}"


class SMSServiceConfig(models.Model):
    name = models.CharField(max_length=50, unique=True, default="default")
    username = models.CharField(max_length=100)
    pin = models.CharField(max_length=255)
    signature = models.CharField(max_length=50)
    dlt_entity_id = models.CharField(max_length=50)
    dlt_template_id = models.CharField(max_length=50, default="1007722920127309405")
    base_url = models.URLField(default="https://smsgw.sms.gov.in/failsafe/MLink")
    message_template = models.TextField(
        default="From eAbkari, GoSK :\nYour OTP is {otp}\n Thanks"
    )
    verify_ssl = models.BooleanField(default=False)
    timeout_seconds = models.PositiveIntegerField(default=10)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "sms_service_config"
        verbose_name = "SMS Service Config"
        verbose_name_plural = "SMS Service Configs"
        ordering = ["-updated_at"]

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.is_active:
            self.__class__.objects.exclude(pk=self.pk).filter(is_active=True).update(is_active=False)

    def __str__(self):
        return f"{self.name} ({'active' if self.is_active else 'inactive'})"


class LicenseeProfile(models.Model):
    """
    Extended profile for licensee users.
    Consolidated from the former core.LicenseeProfile — all personal/demographic
    details now live here alongside the user link and PAN number.
    """

    # ── Link to user ──────────────────────────────────────────────
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='licensee_profile'
    )

    # ── Identity / KYC ───────────────────────────────────────────
    # null=True, blank=True so the migration can run against existing rows.
    # The serializer enforces these as required on create.
    pan_number = models.CharField(max_length=10, unique=True, null=True, blank=True)
    father_name = models.CharField(max_length=100, null=True, blank=True)
    dob = models.DateField(verbose_name='Date of Birth', null=True, blank=True)
    gender = models.CharField(max_length=1, choices=GENDER_CHOICES, null=True, blank=True)
    nationality = models.CharField(max_length=50, null=True, blank=True)

    # ── Personal status ───────────────────────────────────────────
    marital_status = models.CharField(
        max_length=10,
        choices=MARITAL_STATUS_CHOICES,
        null=True,
        blank=True,
    )
    residential_status = models.CharField(
        max_length=20,
        choices=RESIDENTIAL_STATUS_CHOICES,
        null=True,
        blank=True,
    )

    # ── Audit ─────────────────────────────────────────────────────
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='created_licensee_profiles'
    )
    operation_date = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'licensee_profile'
        verbose_name = 'Licensee Profile'
        verbose_name_plural = 'Licensee Profiles'

    def __str__(self):
        return f"LicenseeProfile({self.user})"


class OICOfficerAssignment(models.Model):
    officer = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='oic_assignment'
    )
    approved_application = models.ForeignKey(
        'new_license_application.NewLicenseApplication',
        on_delete=models.PROTECT,
        related_name='oic_officers'
    )
    license = models.ForeignKey(
        'license.License',
        on_delete=models.PROTECT,
        related_name='oic_officers'
    )
    licensee_id = models.CharField(max_length=100)
    establishment_name = models.CharField(max_length=150)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_oic_assignments'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'oic_officers_mapping'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.officer} -> {self.establishment_name}"
