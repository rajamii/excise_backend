from django.db import models
from django.conf import settings

class UserManufacturingUnit(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='manufacturing_units')
    manufacturing_unit_name = models.CharField(max_length=255)
    licensee_id = models.CharField(max_length=100)
    license_type = models.CharField(max_length=100, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'user_manufacturing_units'
        unique_together = ('user', 'licensee_id')

    def __str__(self):
        return f"{self.user.username} - {self.manufacturing_unit_name}"

class SupplyChainUserProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='supply_chain_profile')
    manufacturing_unit_name = models.CharField(max_length=255)
    licensee_id = models.CharField(max_length=100)
    license_type = models.CharField(max_length=100, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username} - {self.manufacturing_unit_name}"

    class Meta:
        db_table = 'supply_chain_user_profile'
