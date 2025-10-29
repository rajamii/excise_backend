from django.contrib import admin
from .models import EnaRequisitionDetail


@admin.register(EnaRequisitionDetail)
class EnaRequisitionDetailAdmin(admin.ModelAdmin):
    list_display = (
        'our_ref_no',
        'requisition_date',
        'lifted_from_distillery_name',
        'status',
        'state',
        'created_at',
    )
    search_fields = ('our_ref_no', 'status', 'state')
    list_filter = ('status', 'state', 'requisition_date')
    date_hierarchy = 'requisition_date'


