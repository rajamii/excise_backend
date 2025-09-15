from django.urls import path
from . import views

app_name = 'company_registration'

urlpatterns = [
    path('', views.company_list, name='list'),
    path('create/', views.company_create, name='create'),
    path('<int:pk>/', views.company_detail, name='detail'),
    path('<int:pk>/update/', views.company_update, name='update'),
    path('<int:pk>/delete/', views.company_delete, name='delete'),
    path('appid/<str:application_id>/', views.company_detail_by_appid, name='detail-by-appid'),
    path('appid/<str:application_id>/update/', views.company_update_by_appid, name='update-by-appid'),
    path('appid/<str:application_id>/delete/', views.company_delete_by_appid, name='delete-by-appid'),
]
