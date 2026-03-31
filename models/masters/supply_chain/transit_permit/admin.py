from django.contrib import admin
from django.contrib.admin.sites import AlreadyRegistered
from .models import BrandMlInCases


class BrandMlInCasesAdmin(admin.ModelAdmin):
    list_display = ('ml', 'pieces_in_case', 'created_at', 'updated_at')
    search_fields = ('ml',)


try:
    admin.site.register(BrandMlInCases, BrandMlInCasesAdmin)
except AlreadyRegistered:
    pass
