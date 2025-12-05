from django.db import models
from django.utils.timezone import now
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from models.masters.core.models import District, LicenseCategory

class License(models.Model):
    SOURCE_TYPES = [
        ('new_license_application', 'New License Application'),
        ('license_application', 'License Application'),
        ('salesman_barman', 'Salesman/Barman'),
    ]

    license_id = models.CharField(max_length=30, primary_key=True, db_index=True, unique=True)

    # application = models.OneToOneField(
    #     LicenseApplication,
    #     on_delete=models.CASCADE,
    #     related_name='issued_license'  # Changed from 'license' to 'issued_license'
    # )

    # Generic Relation
    source_content_type = models.ForeignKey(ContentType, on_delete=models.PROTECT)
    source_object_id = models.CharField(max_length=50)
    source_application = GenericForeignKey('source_content_type', 'source_object_id')

    source_type = models.CharField(max_length=30, choices=SOURCE_TYPES)

    license_category = models.ForeignKey(
        LicenseCategory,
        on_delete=models.PROTECT
    )

    # establishment_name = models.CharField(max_length=255)
    # licensee_name = models.CharField(max_length=100)
    excise_district = models.ForeignKey(
        District,
        on_delete=models.PROTECT,
        related_name='licenses_issued_in_districts'
    )

    issue_date = models.DateField(default=now)
    valid_up_to = models.DateField()
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'licenses'
        ordering = ['-issue_date']
        indexes = [
            models.Index(fields=['license_id']),
            models.Index(fields=['source_type']),
            models.Index(fields=['license_category']),
            models.Index(fields=['is_active']),
            models.Index(fields=['valid_up_to']),
        ]

    def __str__(self):
        return f"{self.license_id} — {self.get_source_type_display()}"

    def save(self, *args, **kwargs):
        if not self.license_id:
            self.license_id = self._generate_license_id()
        super().save(*args, **kwargs)

    def generate_license_id(self) -> str:
        """Generate a unique license ID based on district and financial year."""
        try:
            district_code = str(self.excise_district.district_code).strip()
        except AttributeError:
            raise ValueError("Invalid District object assigned to excise_district.")

        today = now().date()
        year = self.issue_date.year
        month = today.month
        prefix_map = {
            'new_license_application': 'NA',
            'license_application': 'LA',
            'salesman_barman': 'SB',
        }

        prefix = prefix_map.get(self.source_type)

        if month >= 4:
            fin_year = f"{year}-{str(year + 1)[2:]}"
        else:
            fin_year = f"{year - 1}-{str(year)[2:]}"

        prefixx = f"{prefix}/{district_code}/{fin_year}"

        # Sequential number per prefix + district + year
        last = License.objects.filter(
            license_id__startswith=f"{prefixx}/{district_code}/{fin_year}/",
            source_type=self.source_type
        ).order_by('-license_id').first()

        seq = 1
        if last and '/' in last.license_id:
            try:
                seq = int(last.license_id.split('/')[-1]) + 1
            except (ValueError, IndexError):
                pass

        return f"{prefixx}/{district_code}/{fin_year}/{str(seq).zfill(4)}"