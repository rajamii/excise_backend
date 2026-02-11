from django.urls import path
from . import views

app_name = 'roles'

urlpatterns = [
    # Role collection endpoints
    path('', views.role_list, name='role-list'),
    path('create/', views.role_create, name='role-create'),
    path('dashboard-config/current/', views.current_dashboard_config, name='dashboard-config-current'),
    path('dashboard-config/<int:role_id>/', views.dashboard_config_by_role, name='dashboard-config-by-role'),
    
    # Role instance endpoints
    path('<int:pk>/detail/', views.role_detail, name='role-detail'),
    path('<int:pk>/update/', views.role_update, name='role-update'),
    path('<int:pk>/delete/', views.role_delete, name='role-delete'),
]
