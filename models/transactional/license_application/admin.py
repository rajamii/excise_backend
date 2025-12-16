from django.contrib import admin
from .models import LicenseApplication

@admin.register(LicenseApplication)
class LicenseApplicationAdmin(admin.ModelAdmin):
  list_display = ('application_id', 'establishment_name', 'current_stage', 'is_approved')