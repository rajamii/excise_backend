from django.contrib import admin
from .models import CompanyDetails, MemberDetails, DocumentDetails

# Register the models for the admin panel
admin.site.register(CompanyDetails)
admin.site.register(MemberDetails)
admin.site.register(DocumentDetails)
