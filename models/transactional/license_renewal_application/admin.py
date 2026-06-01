from django.contrib import admin
from .models import LicenseApplication

@admin.register(LicenseApplication)
class LicenseApplicationAdmin(admin.ModelAdmin):
  list_display = ('application_id', 'applicant', 'license_category', 'license_sub_category', 'old_license_id', 'is_approved')
