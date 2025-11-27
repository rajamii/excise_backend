# yourapp/admin.py
from django.contrib import admin
from .models import TransitPermitDistributorData

@admin.register(TransitPermitDistributorData)
class TransitPermitDistributorDataAdmin(admin.ModelAdmin):
    list_display = ('id', 'distributor_name', 'manufacturing_unit', 'depo_address', 'created_at')
    search_fields = ('distributor_name', 'manufacturing_unit', 'depo_address')
    readonly_fields = ('created_at', 'updated_at')
