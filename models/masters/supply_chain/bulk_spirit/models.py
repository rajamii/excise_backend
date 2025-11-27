from django.db import models

class BulkSpiritType(models.Model):
    """Model for storing different types of bulk spirits."""
    sprit_id = models.AutoField(primary_key=True)
    strength_from = models.CharField(max_length=100)
    strength_to = models.CharField(max_length=100)
    price_bl = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'ena_bulk_sprit'
        managed = False  # Since the table already exists
        ordering = ['sprit_id']

    def __str__(self):
        return f"{self.strength_from} - {self.strength_to}"
