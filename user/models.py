from django.db import models
from django.contrib.auth.models import AbstractUser, BaseUserManager, PermissionsMixin
from django.core.exceptions import ObjectDoesNotExist
from .validators import validate_name, validate_Numbers  
import random


class CustomUserManager(BaseUserManager):
    """Custom manager for the CustomUser model."""

    # Method for creating a user with the necessary fields
    def create_user(self, email, password=None, role=None, **extra_fields):
        if not email:
            raise ValueError('The Email field must be set')
        
        # Generate a unique username based on certain fields
        username = self.generate_unique_username(
            extra_fields['first_name'],
            extra_fields['last_name'],
            extra_fields['phonenumber'],
            extra_fields['district'],
            extra_fields['subdivision']
        )

        # Remove username if passed
        extra_fields.pop('username', None)

        user = self.model(email=email, username=username, role=role, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def generate_unique_username(self, first_name, last_name, phone_number, district, subdivision):
        initials = first_name[0].upper() + last_name[0].upper()
        base_username = f"{initials}{phone_number[-4:]}{district}{subdivision}"
        username = base_username[:10]
        while self.model.objects.filter(username=username).exists():
            username = f"{base_username[:7]}{random.randint(100, 999)}"
        return username

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('first_name', 'Admin')
        extra_fields.setdefault('last_name', 'User')
        extra_fields.setdefault('phonenumber', '9999999999')
        extra_fields.setdefault('district', 117)
        extra_fields.setdefault('subdivision', 1001)
        return self.create_user(email, password, role='site_admin', **extra_fields)


class CustomUser(AbstractUser, PermissionsMixin):
    """Custom user model extending AbstractUser."""
    
    ROLE_CHOICES = (
        ('site_admin', 'Site Admin'),
        ('commissioner', 'Commissioner'),
        ('joint_commissioner', 'Joint Commissioner'),
        ('permit_section','Permit Section'),
        ('2', 'Licensee'),
    )
    role = models.CharField(max_length=30, choices=ROLE_CHOICES, default='2')

    class Meta:
        db_table = 'custom_user'

    email = models.EmailField(unique=True)
    role = models.CharField(max_length=19, choices=ROLE_CHOICES)
    first_name = models.CharField(max_length=50, null=False, validators=[validate_name])
    middle_name = models.CharField(max_length=50, null=True, validators=[validate_name])
    last_name = models.CharField(max_length=50, null=False, validators=[validate_name])
    phonenumber = models.CharField(max_length=10, default='9999999999', validators=[validate_Numbers])
    district = models.IntegerField(default=117)
    subdivision = models.IntegerField(default=1001)
    address = models.CharField(max_length=70, null=True)
    created_by = models.CharField(max_length=70, null=True)

    objects = CustomUserManager()

    def __str__(self):
        return self.username

    class Meta:
        permissions = []
