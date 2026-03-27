from django.contrib import admin

from .master_license_form import MasterLicenseForm


@admin.register(MasterLicenseForm)
class MasterLicenseFormAdmin(admin.ModelAdmin):
    list_display = ("license_title", "licensee_cat_code", "licensee_scat_code", "updated_at")
    list_filter = ("licensee_cat_code", "licensee_scat_code")
    search_fields = ("license_title",)
