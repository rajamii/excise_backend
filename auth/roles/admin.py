from django.contrib import admin
from .models import Role, DashboardRoleConfig


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'role_precedence')
    search_fields = ('name',)


@admin.register(DashboardRoleConfig)
class DashboardRoleConfigAdmin(admin.ModelAdmin):
    list_display = ('role', 'layout', 'is_active', 'config_version', 'updated_at')
    list_filter = ('layout', 'is_active')
    search_fields = ('role__name',)
