from django.contrib import admin

from .models import (
    DistributorPermitApplication,
    DistributorPermitDocument,
    DistributorPermitLineItem,
)


class DistributorPermitLineItemInline(admin.TabularInline):
    model = DistributorPermitLineItem
    extra = 0
    readonly_fields = (
        'brand_name',
        'pieces_per_case',
        'edp_per_case',
        'import_pass_fee_per_case',
        'mrp_per_bottle',
        'additional_ed_per_case',
        'education_cess_per_case',
        'total_additional_ed',
        'bulk_litres',
        'permit_number',
    )


class DistributorPermitDocumentInline(admin.TabularInline):
    model = DistributorPermitDocument
    extra = 0


@admin.register(DistributorPermitApplication)
class DistributorPermitApplicationAdmin(admin.ModelAdmin):
    list_display = ('reference_no', 'applicant', 'supplier_company_name', 'status', 'submitted_at')
    search_fields = ('reference_no', 'supplier_company_name', 'applicant__username', 'applicant__email')
    list_filter = ('status', 'submitted_at')
    inlines = [DistributorPermitLineItemInline, DistributorPermitDocumentInline]
