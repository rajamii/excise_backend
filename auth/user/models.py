from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager
from django.core.validators import validate_email
from django.db.models.functions import Abs
from auth.user.validators import validate_name, validate_phone_number
from auth.roles.models import Role
from django.utils import timezone
import uuid
import random

class CustomUserManager(BaseUserManager):
    def create_user(self, email, first_name, last_name, phone_number,
                   district, subdivision, address, password=None, **extra_fields):
        """
        Creates and saves a User with the given required fields
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

    def generate_unique_username(self, first_name, last_name, phone_number, district, subdivision):
        initials = f"{first_name[0].upper()}{last_name[0].upper()}"
        base = f"{initials}{phone_number[-4:]}{district}{subdivision}"
        username = base[:10]
        
        while self.model.objects.filter(username=username).exists():
            username = f"{base[:7]}{random.randint(100, 999)}"
        return username

class CustomUser(AbstractBaseUser):
    email = models.EmailField(
        unique=True,
        validators=[validate_email],
        error_messages={
            'unique': "A user with that email already exists.",
        }
    )
    username = models.CharField(
        max_length=30,
        unique=True,
        blank=True  # Will be auto-generated
    )
    first_name = models.CharField(
        max_length=50,
        validators=[validate_name],
        error_messages={
            'blank': "First name cannot be blank.",
        }
    )
    middle_name = models.CharField(
        max_length=50,
        validators=[validate_name],
        blank=True
    )
    last_name = models.CharField(
        max_length=50,
        validators=[validate_name],
        error_messages={
            'blank': "Last name cannot be blank.",
        }
    )
    phone_number = models.CharField(
        max_length=10,
        unique=True,
        validators=[validate_phone_number],
        error_messages={
            'unique': "A user with that phone number already exists.",
        }
    )
    district = models.PositiveIntegerField(default=117)# pyright: ignore [reportArgumentType, reportGeneralTypeIssues] 
    subdivision = models.PositiveIntegerField(default=1001)# pyright: ignore [reportArgumentType, reportGeneralTypeIssues]
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
    is_active = models.BooleanField(default=True)# pyright: ignore [reportArgumentType, reportGeneralTypeIssues]
    date_joined = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey('self',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='created_users'
    )

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
    
    def clean_expired_otps():
        OTP.objects.filter(used=False, created_at__lt=timezone.now() - timezone.timedelta(minutes=10)).delete()

    def __str__(self):
        return f"{self.phone_number} - {self.otp}"   
 
