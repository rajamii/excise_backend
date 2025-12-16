from django.contrib import admin
from .models import EnaCancellationDetail

@admin.register(EnaCancellationDetail)
class EnaCancellationDetailAdmin(admin.ModelAdmin):
    list_display = ('our_ref_no', 'distillery_name', 'status', 'requisition_date')
    search_fields = ('our_ref_no', 'distillery_name', 'licensee_id')
    list_filter = ('status', 'state')
    date_hierarchy = 'requisition_date'
