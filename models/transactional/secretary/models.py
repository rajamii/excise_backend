from django.db import models


class SecretaryBulkSpiritLog(models.Model):
    """
    Audit log / record of Secretary overview views, factory inspection notes,
    or capacity quota reviews.
    """
    factory_name = models.CharField(max_length=255)
    license_number = models.CharField(max_length=100, blank=True, null=True)
    sub_category = models.CharField(max_length=100)  # Distillery / Brewery
    district = models.CharField(max_length=100, blank=True, null=True)
    stock_bl = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    remarks = models.TextField(blank=True, null=True)
    reviewed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'secretary_bulk_spirit_log'
        ordering = ['-reviewed_at']
        verbose_name = 'Secretary Bulk Spirit Log'
        verbose_name_plural = 'Secretary Bulk Spirit Logs'

    def __str__(self):
        return f"SecretaryLog<{self.factory_name} ({self.sub_category})>"
