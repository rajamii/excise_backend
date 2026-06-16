from django.contrib import admin

from .models import MasterHologramSupplier


@admin.register(MasterHologramSupplier)
class MasterHologramSupplierAdmin(admin.ModelAdmin):
    list_display = ('company_name', 'state', 'is_active', 'updated_at')
    list_filter = ('is_active', 'state')
    search_fields = ('company_name', 'state', 'address', 'post')

