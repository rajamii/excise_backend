from django.db import models
from django.db import IntegrityError


class Role(models.Model):
    name = models.CharField(max_length=100, unique=True)

    READ = 'read'
    READ_WRITE = 'read_write'
    NONE = 'none'

    PERMISSION_CHOICES = [
        (READ, 'Read'),
        (READ_WRITE, 'Read & Write'),
        (NONE, 'None'),
    ]

    company_registration_access = models.CharField(
        max_length=10,
        choices=PERMISSION_CHOICES,
        default=NONE,
        verbose_name='Company Registration Access'
    )
    contact_us_access = models.CharField(
        max_length=10,
        choices=PERMISSION_CHOICES,
        default=NONE,
        verbose_name='Contact Us Access'
    )
    license_application_access = models.CharField(
        max_length=10,
        choices=PERMISSION_CHOICES,
        default=NONE,
        verbose_name='License Application Access'
    )
    masters_access = models.CharField(
        max_length=10,
        choices=PERMISSION_CHOICES,
        default=NONE,
        verbose_name='Masters Access'
    )
    roles_access = models.CharField(
        max_length=10,
        choices=PERMISSION_CHOICES,
        default=NONE,
        verbose_name='Roles Access'
    )
    salesman_barman_registration_access = models.CharField(
        max_length=10,
        choices=PERMISSION_CHOICES,
        default=NONE,
        verbose_name='Salesman/Barman Access'
    )
    user_access = models.CharField(
        max_length=10,
        choices=PERMISSION_CHOICES,
        default=NONE,
        verbose_name='User Access'
    )

    def __str__(self):
        return self.name


    def create_dev_role():

        try:
            Role.objects.create(
                name='dev',
                company_registration_access=Role.READ_WRITE,
                contact_us_access=Role.READ_WRITE,
                license_application_access=Role.READ_WRITE,
                masters_access=Role.READ_WRITE,
                roles_access=Role.READ_WRITE,
                salesman_barman_registration_access=Role.READ_WRITE,
                user_access=Role.READ_WRITE,
            )
            print("Successfully created 'dev' role.")  # Added helpful output
        except IntegrityError:
            print("'dev' role already exists.")  # Handle the case where the role already exists


def call_create_dev_role():
    """
    Helper function to call create_dev_role().  Useful for calling
    from places where you might not want to deal with the direct import.
    """

    Role.create_dev_role()


if __name__ == "__main__":
    call_create_dev_role()



