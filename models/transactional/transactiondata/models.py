from django.db import models
from auth.user.models import CustomUser
from models.masters.license.models import License
from models.masters.core.models import District, Subdivision, LicenseCategory
from django.core.validators import FileExtensionValidator

class TransactionData(models.Model):
    licensee_id = models.ForeignKey(
        License,
        on_delete=models.CASCADE,
        related_name='transactions',
        to_field='license_id'
    )
    district = models.ForeignKey(
        District,
        on_delete=models.CASCADE,
        related_name='transactions',
        to_field='district_code'
    )
    subdivision = models.ForeignKey(
        Subdivision,
        on_delete=models.CASCADE,
        related_name='transactions',
        to_field='subdivision_code'
    )
    license_category = models.ForeignKey(
        LicenseCategory,
        on_delete=models.SET_NULL,
        null=True,
        related_name='transactions',
        to_field='id'
    )
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    file = models.FileField(
        upload_to='transaction_files/', 
        null=True, 
        blank=True,
        validators=[FileExtensionValidator(allowed_extensions=['pdf', 'jpg', 'jpeg', 'png'])]
        )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        related_name='updated_transactions'
    )

    def __str__(self):
        return f"Transaction for {self.licensee_id.username}"

    class Meta:
        db_table = 'transaction_data'
        