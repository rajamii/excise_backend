from django.contrib import admin
from .models import LicenseApplication, LicenseApplicationTransaction

@admin.register(LicenseApplication)
class LicenseApplicationAdmin(admin.ModelAdmin):
    list_display = ('id', 'establishmentName', 'current_stage', 'is_approved')

@admin.register(LicenseApplicationTransaction)
class LicenseApplicationTransactionAdmin(admin.ModelAdmin):
    list_display = ('license_application', 'stage', 'performed_by', 'timestamp')
