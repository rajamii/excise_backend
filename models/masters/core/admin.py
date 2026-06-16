from django.contrib import admin

from .models import SupplyChainTimerConfig, RenewalApplicationConfig


@admin.register(SupplyChainTimerConfig)
class SupplyChainTimerConfigAdmin(admin.ModelAdmin):
    list_display = ('code', 'delay_value', 'delay_unit', 'is_active', 'updated_at')
    list_filter = ('delay_unit', 'is_active')
    search_fields = ('code', 'description')

@admin.register(RenewalApplicationConfig)
class RenewalApplicationConfigAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'renewal_month', 'renewal_day', 'renewal_time')
