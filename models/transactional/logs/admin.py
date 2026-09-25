from django.contrib import admin
from .models import UserActivity, AdminLog

@admin.register(AdminLog)
class AdminLogAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'timestamp',
        'username',
        'full_name',
        'role',
        'action',
        'module_name',
        'application_id',
        'from_stage',
        'to_stage_name',
        'to_stage_username'
    )
    list_filter = ('action', 'module_name', 'role', 'timestamp')
    search_fields = (
        'username',
        'full_name',
        'role',
        'module_name',
        'application_id',
        'to_stage_name',
        'to_stage_username',
        'remarks',
        'admin_id'
    )

    readonly_fields = [f.name for f in AdminLog._meta.fields]
    ordering = ('-timestamp',)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(UserActivity)
class UserActivityAdmin(admin.ModelAdmin):
    list_display = ('id', 'timestamp', 'user', 'activity_type', 'ip_address')
    list_filter = ('activity_type', 'timestamp')
    search_fields = ('user__username', 'user__email', 'ip_address')
    readonly_fields = [f.name for f in UserActivity._meta.fields]
    ordering = ('-timestamp',)

