from django.urls import path
from .views import (
    user_activity_list,
    track_custom_activity,
    admin_log_list,
    admin_log_history,
    admin_log_modules,
    admin_log_actions,
    admin_log_roles,
    track_admin_log,
)

urlpatterns = [
    path('activities/', user_activity_list, name='user-activity-list'),
    path('activities/track/', track_custom_activity, name='track-activity'),
    
    # Admin Audit Logs ('admin_log' table)
    path('admin-logs/', admin_log_list, name='admin-log-list'),
    path('admin-logs/history/<str:application_id>/', admin_log_history, name='admin-log-history'),
    path('admin-logs/modules/', admin_log_modules, name='admin-log-modules'),
    path('admin-logs/actions/', admin_log_actions, name='admin-log-actions'),
    path('admin-logs/roles/', admin_log_roles, name='admin-log-roles'),
    path('admin-logs/track/', track_admin_log, name='admin-log-track'),

    # Underscore aliases for compatibility
    path('admin_logs/', admin_log_list, name='admin-log-list-alt'),
    path('admin_logs/history/<str:application_id>/', admin_log_history, name='admin-log-history-alt'),
]

