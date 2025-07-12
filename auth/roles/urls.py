from django.urls import path
from . import views

app_name = 'roles'

urlpatterns = [
    # Role collection endpoints
    path('', views.role_list, name='role-list'),
    path('create/', views.role_create, name='role-create'),
    
    # Role instance endpoints
    path('<int:pk>/detail/', views.role_detail, name='role-detail'),
    path('<int:pk>/update/', views.role_update, name='role-update'),
    path('<int:pk>/delete/', views.role_delete, name='role-delete'),
]
