from django.contrib import admin
from .models import CompanyRegistration


@admin.register(CompanyRegistration)
class CompanyRegistrationAdmin(admin.ModelAdmin):
    list_display = ('application_id', 'company_name', 'current_stage', 'is_approved')
