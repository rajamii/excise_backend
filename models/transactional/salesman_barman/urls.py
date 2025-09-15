from django.urls import path
from . import views

app_name = 'salesman_barman'

urlpatterns = [
    path('', views.salesman_barman_list, name='list'),
    path('create/', views.salesman_barman_create, name='create'),
    path('<int:pk>/', views.salesman_barman_detail, name='detail'),
    path('<int:pk>/update/', views.salesman_barman_update, name='update'),
    path('<int:pk>/delete/', views.salesman_barman_delete, name='delete'),
    path('appid/<str:application_id>/', views.salesman_barman_detail_by_appid, name='detail-by-appid'),
    path('appid/<str:application_id>/update/', views.salesman_barman_update_by_appid, name='update-by-appid'),
    path('appid/<str:application_id>/delete/', views.salesman_barman_delete_by_appid, name='delete-by-appid'),
]
