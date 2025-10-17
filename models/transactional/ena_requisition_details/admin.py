from django.contrib import admin
from .models import EnaRequisitionDetail


@admin.register(EnaRequisitionDetail)
class EnaRequisitionDetailAdmin(admin.ModelAdmin):
    list_display = (
        'requisition_number',
        'application_id',
        'requested_on',
        'quantity_liters',
        'status',
        'created_at',
    )
    search_fields = ('requisition_number', 'application_id', 'status')
    list_filter = ('status', 'requested_on')


