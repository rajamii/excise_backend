from django.contrib import admin
from .models import BrandMlInCases

@admin.register(BrandMlInCases)
class BrandMlInCasesAdmin(admin.ModelAdmin):
    list_display = ('ml', 'pieces_in_case', 'created_at', 'updated_at')
    search_fields = ('ml',)
