from django.db import models

class TransitPermitBottleType(models.Model):
    bottle_type = models.CharField(max_length=100, unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'transit_permit_bottle_types'
        verbose_name = 'Transit Permit Bottle Type'
        verbose_name_plural = 'Transit Permit Bottle Types'

    def __str__(self):
        return self.bottle_type
