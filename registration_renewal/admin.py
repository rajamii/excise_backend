from django.contrib import admin
from .models import CompanyDetails, MemberDetails, DocumentDetails

# Register the models for the admin panel
admin.site.register(CompanyDetails)
class CompanyDetailsAdmin(admin.ModelAdmin):
    list_display = ('name', 'license_type', 'application_year', 'country', 'state')  # Ensure 'license_type' is included
admin.site.register(MemberDetails)
admin.site.register(DocumentDetails)
