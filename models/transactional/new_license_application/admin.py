from django.contrib import admin
from .models import NewLicenseApplication


@admin.register(NewLicenseApplication)
class NewLicenseApplicationAdmin(admin.ModelAdmin):
    list_display = ('application_id', 'applicant_name', 'current_stage', 'is_approved')
