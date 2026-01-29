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

class BrandMlInCases(models.Model):
    ml = models.IntegerField(db_column='ml', unique=True)
    pieces_in_case = models.IntegerField(db_column='pieces_in_case')
    created_at = models.DateTimeField(auto_now_add=True, blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True, blank=True, null=True)

    class Meta:
        db_table = 'brand_ml_in_cases'
        unique_together = (('ml', 'pieces_in_case'),)
        verbose_name = 'Brand ML in Cases'
        verbose_name_plural = 'Brand ML in Cases'

    def __str__(self):
        return f"{self.ml} ml - {self.pieces_in_case} pieces"
