from django.db import models
from django.utils.timezone import now
from django.db import transaction
from models.transactional.license_application.models import LicenseApplication
from models.masters.core.models import LicenseType, District

class License(models.Model):
    license_id = models.CharField(max_length=30, primary_key=True, db_index=True)
    application = models.OneToOneField(
        LicenseApplication,
        on_delete=models.CASCADE,
        related_name='issued_license'  # Changed from 'license' to 'issued_license'
    )
    license_type = models.ForeignKey(
        LicenseType,
        on_delete=models.PROTECT
    )
    establishment_name = models.CharField(max_length=255)
    licensee_name = models.CharField(max_length=100)
    excise_district = models.ForeignKey(
        District,
        on_delete=models.PROTECT,
        related_name='licenses_issued_in_districts'
    )
    issue_date = models.DateField(default=now)
    valid_up_to = models.DateField()
    is_active = models.BooleanField(default=True)

    def generate_license_id(self):
        """Generate a unique license ID based on district and financial year."""
        try:
            district_code = str(self.excise_district.district_code).strip()
        except AttributeError:
            raise ValueError("Invalid District object assigned to excise_district.")

        today = now().date()
        year = today.year
        month = today.month
        if month >= 4:
            fin_year = f"{year}-{str(year + 1)[2:]}"
        else:
            fin_year = f"{year - 1}-{str(year)[2:]}"

        prefix = f"{district_code}/{fin_year}"

        with transaction.atomic():
            last_license = License.objects.filter(
                license_id__startswith=prefix
            ).order_by('-license_id').first()

            if last_license and last_license.license_id:
                last_number_str = last_license.license_id.split('/')[-1]
                try:
                    last_number = int(last_number_str)
                except ValueError:
                    last_number = 0
            else:
                last_number = 0

            new_number = last_number + 1
            new_number_str = str(new_number).zfill(4)

            return f"{prefix}/{new_number_str}"

    def save(self, *args, **kwargs):
        if not self.license_id:
            self.license_id = self.generate_license_id()
        super().save(*args, **kwargs)

    class Meta:
        db_table = 'license'
        indexes = [
            models.Index(fields=['excise_district']),
            models.Index(fields=['license_type']),
            models.Index(fields=['is_active']),
        ]

    def __str__(self):
        return f"License {self.license_id} for {self.establishment_name}"