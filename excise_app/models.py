from django.db import models
from django.contrib.auth.models import AbstractUser, BaseUserManager, PermissionsMixin
from .validators import validate_name, validate_Numbers 
import random

class CustomUserManager(BaseUserManager):
    def create_user(self, email, password=None, role=None, **extra_fields):
        if not email:
            raise ValueError('The Email field must be set')
        
        # Generate a unique username based on initials, phone number, district, and subdivision

        username = self.generate_unique_username(extra_fields['first_name'], extra_fields['last_name'], extra_fields['phonenumber'], extra_fields['district'], extra_fields['subdivision'])

        user = self.model(email=email, username=username, role=role, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def generate_unique_username(self, first_name, last_name, phone_number, district, subdivision):
        # Get initials and create a base username

        initials = first_name[0].upper() + last_name[0].upper()
        base_username = f"{initials}{phone_number[-4:]}{district}{subdivision}"
        
        # Ensure username is unique, adding random digits if needed

        username = base_username[:10] if len(base_username) >= 10 else base_username  # Truncate to 10 characters if needed
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


# Custom User Model
class CustomUser(AbstractUser, PermissionsMixin):
    ROLE_CHOICES = (
        ('site_admin', 'site_admin'),
        ('1', 'system_admin'),
        ('2', 'licensee'),
    )
    email = models.EmailField(unique=True)
    role = models.CharField(max_length=19, choices=ROLE_CHOICES)
    first_name = models.CharField(max_length=50, null=False , validators=[validate_name])
    middle_name = models.CharField(max_length=50, null=True , validators=[validate_name])
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


# # District Model
# class District(models.Model):
#     District = models.CharField(max_length=30, validators=[validate_name])
#     DistrictNameLL = models.CharField(max_length=30, validators=[validate_name], null=True)
#     DistrictCode = models.IntegerField(unique=True, default=117)
#     IsActive = models.BooleanField(default=True)
#     StateCode = models.ForeignKey(
#         'State', to_field='StateCode', on_delete=models.CASCADE, related_name='districts', null=True
#     )

#     def __str__(self):
#         return self.District


# # Subdivision Model
# class Subdivision(models.Model):
#     SubDivisionName = models.CharField(max_length=30, validators=[validate_name], null=True)
#     SubDivisionNameLL = models.CharField(max_length=30, validators=[validate_name], null=True)
#     SubDivisionCode = models.IntegerField(unique=True, default=1001)
#     IsActive = models.BooleanField(default=True)
#     DistrictCode = models.ForeignKey(
#         District, to_field='DistrictCode', on_delete=models.CASCADE, related_name='subdivisions', null=True
#     )

#     def __str__(self):
#         return self.Subdivision

# # State Model
# class State(models.Model):
#     State = models.CharField(max_length=100, default='Sikkim')  # Specify max_length
#     StateNameLL = models.CharField(max_length=30, validators=[validate_name])
#     StateCode = models.IntegerField(unique=True, default=11)
#     IsActive = models.BooleanField(default=True)

#     def __str__(self):
#         return self.State
