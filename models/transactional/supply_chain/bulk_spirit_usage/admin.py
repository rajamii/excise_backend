from django.contrib import admin
from .models import EnaBulkSpiritUsage

@admin.register(EnaBulkSpiritUsage)
class EnaBulkSpiritUsageAdmin(admin.ModelAdmin):
    list_display = ('reference_no', 'licensee_id', 'bulk_spirit_type', 'quantity', 'status', 'created_at')
    search_fields = ('reference_no', 'licensee_id', 'bulk_spirit_type', 'distillery_name')
    list_filter = ('status', 'bulk_spirit_type')
