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

    license_id = models.CharField(max_length=50, primary_key=True, db_index=True, unique=True)

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

    print_count = models.PositiveIntegerField(default=0)
    is_print_fee_paid = models.BooleanField(default=False)
    printed_on = models.DateTimeField(null=True, blank=True)
    print_fee_paid_on = models.DateTimeField(null=True, blank=True)

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
    
    def can_print_license(self):
        if self.print_count < 5:
            return True, 0  # Allowed to print, no fee required
        elif self.is_print_fee_paid:
            return True, 500  # Allowed to print, fee has been paid
        else:
            return False, 500  # Not allowed, fee required

    def record_license_print(self, fee_paid=False):
        self.print_count += 1
        if self.print_count > 5 and fee_paid:
            self.is_print_fee_paid = True
        self.save()

    def save(self, *args, **kwargs):
        if not self.license_id:
            self.license_id = self.generate_license_id()
        super().save(*args, **kwargs)

    def generate_license_id(self) -> str:
        """Generate a unique license ID based on source_type, district and financial year."""
        try:
            district_code = str(self.excise_district.district_code).strip()
        except AttributeError:
            raise ValueError("Invalid or missing excise_district on License creation.")

        # Determine financial year (April–March)
        today = now().date()
        issue_year = self.issue_date.year if self.issue_date else today.year
        if today.month >= 4:
            fin_year = f"{issue_year}-{str(issue_year + 1)[2:]}"
        else:
            fin_year = f"{issue_year - 1}-{str(issue_year)[2:]}"

        # Prefix based on source
        prefix_map = {
            'new_license_application': 'NA',
            'license_application': 'LA',
            'salesman_barman': 'SB',
        }
        prefix = prefix_map.get(self.source_type, 'XX')  # fallback

        base_prefix = f"{prefix}/{district_code}/{fin_year}"

        # Find last sequence number for this exact prefix
        last_license = License.objects.filter(
            license_id__startswith=base_prefix + "/"
        ).order_by('-license_id').first()

        if last_license and '/' in last_license.license_id:
            try:
                seq = int(last_license.license_id.split('/')[-1]) + 1
            except (ValueError, IndexError):
                seq = 1
        else:
            seq = 1

        new_license_id = f"{base_prefix}/{str(seq).zfill(4)}"

        # Final safety: ensure it fits in DB field
        if len(new_license_id) > 30:
            raise ValueError(f"Generated license_id '{new_license_id}' exceeds 30 characters")

        return new_license_id