from django.contrib import admin
from .models import EnaRequisitionDetail, EnaRevalidationActivationSchedule


@admin.register(EnaRequisitionDetail)
class EnaRequisitionDetailAdmin(admin.ModelAdmin):
    list_display = (
        'requisiton_number_of_permits',
        'our_ref_no',
        'requisition_date',
        'status',
        'created_at',
    )
    search_fields = ('our_ref_no', 'status', 'lifted_from_distillery_name')
    list_filter = ('status', 'requisition_date', 'created_at')


@admin.register(EnaRevalidationActivationSchedule)
class EnaRevalidationActivationScheduleAdmin(admin.ModelAdmin):
    list_display = (
        'requisition_ref_no',
        'approval_date',
        'activation_due_at',
        'activated_at',
        'status',
        'updated_at',
    )
    search_fields = ('requisition_ref_no', 'notes')
    list_filter = ('status', 'approval_date', 'activation_due_at', 'activated_at')


