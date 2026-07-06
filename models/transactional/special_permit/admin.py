from django.contrib import admin

from .models import SpecialPermitApplication


@admin.register(SpecialPermitApplication)
class SpecialPermitApplicationAdmin(admin.ModelAdmin):
    list_display = (
        'application_id',
        'license',
        'applicant',
        'financial_year',
        'permission_duration',
        'current_stage',
        'is_approved',
        'created_at',
    )
    list_filter = ('permission_duration', 'is_approved', 'is_fee_paid', 'current_stage')
    search_fields = ('application_id', 'license__license_id', 'applicant__username')
    readonly_fields = ('application_id', 'created_at', 'updated_at')
