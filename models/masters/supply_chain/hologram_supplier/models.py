from django.db import models


class MasterHologramSupplier(models.Model):
    company_name = models.CharField(max_length=255, unique=True)
    post = models.CharField(max_length=255, blank=True, default="")
    address = models.TextField(blank=True, default="")
    state = models.CharField(max_length=100, blank=True, default="")
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'master_hologram_supplier'
        ordering = ['company_name']

    def __str__(self) -> str:
        return self.company_name

