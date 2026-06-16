from django.contrib import admin
from .models import BulkSpiritType

@admin.register(BulkSpiritType)
class BulkSpiritTypeAdmin(admin.ModelAdmin):
    list_display = ('sprit_id', 'bulk_spirit_kind_type', 'strength', 'price_bl', 'license_id', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('bulk_spirit_kind_type', 'strength', 'license_id')
    ordering = ('sprit_id',)
