from django.db import models
from django.contrib.auth.models import (AbstractUser,
                                        BaseUserManager,
                                        PermissionsMixin)
from .validators import validate_name, validate_numbers
from roles.models import Role
from django.utils import timezone
import uuid 
import random

# from django.core.exceptions import ObjectDoesNotExist


class CustomUserManager(BaseUserManager):
    """Custom manager for the CustomUser model."""

    # Method for creating a user with the necessary fields
    def create_user(self, email, password=None, **extra_fields):
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

        user = self.model(email=email,
                          username=username,
                          **extra_fields)

        user.set_password(password)
        user.save(using=self._db)
        return user

    def generate_unique_username(self,
                                 first_name,
                                 last_name,
                                 phone_number,
                                 district,
                                 subdivision):

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

        return self.create_user(email,
                                password,
                                role='site_admin',
                                **extra_fields)



class CustomUser(AbstractUser, PermissionsMixin):
    """Custom user model extending AbstractUser."""

    class Meta:

        db_table = 'custom_user'
        permissions = []

    role = models.ForeignKey(Role,
                             on_delete=models.SET_NULL,
                             null=True,
                             )

    email = models.EmailField(unique=True)

    first_name = models.CharField(max_length=50,
                                  null=False,
                                  validators=[validate_name])

    middle_name = models.CharField(max_length=50,
                                   null=True,
                                   blank=True,
                                   validators=[validate_name])

    last_name = models.CharField(max_length=50,
                                 null=False,
                                 validators=[validate_name])

    phonenumber = models.CharField(max_length=10,
                                   default='9999999999',
                                   validators=[validate_numbers])

    district = models.IntegerField(default=117)
    subdivision = models.IntegerField(default=1001)
    address = models.CharField(max_length=70, null=True)
    # created_by = models.CharField(max_length=70, null=True, blank=True)
    created_by = models.ForeignKey('self',
                                   null=True,
                                   blank=True,
                                   on_delete=models.SET_NULL,
                                   related_name='created_users'
    )

    objects = CustomUserManager()

    def create_dev_user(self):
        Role.create_dev_role()
        role = Role.objects.filter(name='dev').get()

        user = self.model(role=role,
                          username='dev',
                          password='1234567890',
                          email='dev@server.com',
                          first_name='dev',
                          middle_name='dev',
                          last_name='dev',
                          phonenumber='0000000000',
                          )

        print('Please remember this if you are the admin\n\n')
        print('username : dev ')
        print('password : 1234567890\n\n')

        user.save()

    def __str__(self):
        return self.username
    

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




