from django.contrib import admin
from .models import TransitPermitBottleType

@admin.register(TransitPermitBottleType)
class TransitPermitBottleTypeAdmin(admin.ModelAdmin):
    list_display = ('bottle_type', 'is_active', 'created_at', 'updated_at')
    search_fields = ('bottle_type',)
    list_filter = ('is_active',)
