from django.contrib import admin
from .models import BulkSpiritType

@admin.register(BulkSpiritType)
class BulkSpiritTypeAdmin(admin.ModelAdmin):
    list_display = ('sprit_id', 'strength_from', 'strength_to', 'price_bl', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('strength_from', 'strength_to')
    ordering = ('sprit_id',)
