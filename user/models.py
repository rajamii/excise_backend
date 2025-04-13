from django.db import models
from django.contrib.auth.models import AbstractUser, BaseUserManager, PermissionsMixin
from django.core.exceptions import ObjectDoesNotExist
from .validators import validate_name, validate_Numbers  # Custom validators for name and phone number
import random  # For generating random numbers to ensure unique usernames

# Custom manager for the CustomUser model
class CustomUserManager(BaseUserManager):

    # This method has been commented out in the original code, but it could be used for retrieving users
    # def get(self, username):
    #     try:
    #         return self.model.objects.get(username=username)
    #     except ObjectDoesNotExist:
    #         return None

    # Method for creating a user with the necessary fields
    def create_user(self, email, password=None, role=None, **extra_fields):
        if not email:
            raise ValueError('The Email field must be set')
        
        # Generate a unique username based on certain fields provided in extra_fields
        username = self.generate_unique_username(
            extra_fields['first_name'],
            extra_fields['last_name'],
            extra_fields['phonenumber'],
            extra_fields['district'],
            extra_fields['subdivision']
        )

        # Remove the username field from extra_fields (as it is auto-generated)
        extra_fields.pop('username', None)

        # Create the user instance and set the password
        user = self.model(email=email, username=username, role=role, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)  # Save the user instance to the database
        return user

    # Method to generate a unique username based on initials, phone number, district, and subdivision
    def generate_unique_username(self, first_name, last_name, phone_number, district, subdivision):
        # Generate initials from the first and last name
        initials = first_name[0].upper() + last_name[0].upper()
        
        # Construct a base username using the initials, last 4 digits of the phone number, district, and subdivision
        base_username = f"{initials}{phone_number[-4:]}{district}{subdivision}"
        
        # Limit the username to 10 characters and check if it already exists in the database
        username = base_username[:10]
        while self.model.objects.filter(username=username).exists():  # Ensure uniqueness
            # If username exists, append a random 3-digit number to the base username
            username = f"{base_username[:7]}{random.randint(100, 999)}"
        
        return username

    # Method for creating a superuser (admin) with default values for extra fields
    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)  # Ensure the user has staff privileges
        extra_fields.setdefault('is_superuser', True)  # Ensure the user has superuser privileges
        extra_fields.setdefault('first_name', 'Admin')  # Default first name for superuser
        extra_fields.setdefault('last_name', 'User')  # Default last name for superuser
        extra_fields.setdefault('phonenumber', '9999999999')  # Default phone number for superuser
        extra_fields.setdefault('district', 117)  # Default district for superuser
        extra_fields.setdefault('subdivision', 1001)  # Default subdivision for superuser
        return self.create_user(email, password, role='site_admin', **extra_fields)

# Custom user model extending AbstractUser and PermissionsMixin
class CustomUser(AbstractUser, PermissionsMixin):

    # Define available roles for the user
    ROLE_CHOICES = (
        ('site_admin', 'site_admin'),
        ('1', 'system_admin'),
        ('2', 'licensee'),
    )

    # Define the fields for the custom user model
    email = models.EmailField(unique=True)  # Email field, must be unique
    role = models.CharField(max_length=19, choices=ROLE_CHOICES)  # Role field with predefined choices

    # Name fields with validation to ensure proper formatting
    first_name = models.CharField(max_length=50, null=False, validators=[validate_name])  # First name
    middle_name = models.CharField(max_length=50, null=True, validators=[validate_name])  # Middle name (optional)
    last_name = models.CharField(max_length=50, null=False, validators=[validate_name])  # Last name

    # Phone number field with a validator
    phonenumber = models.CharField(max_length=10, default='9999999999', validators=[validate_Numbers])  # Default number

    # District and subdivision fields, with default values
    district = models.IntegerField(default=117)  # Default district value
    subdivision = models.IntegerField(default=1001)  # Default subdivision value
    
    # Address field (optional)
    address = models.CharField(max_length=70, null=True)

    # User creation and modification tracking field
    created_by = models.CharField(max_length=70, null=True)

    # Assigning the custom manager to the CustomUser model
    objects = CustomUserManager()

    def __str__(self):
        return self.username

    class Meta:
        permissions = [] 