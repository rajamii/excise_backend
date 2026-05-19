from django.urls import path
from . import views

app_name = 'ena_distillery_details'

urlpatterns = [
    path('', views.enaDistilleryTypesListAPIView.as_view(), name='ena-distillery-types-list'),
    # Site admin CRUD
    path('admin/', views.distillery_admin_list, name='ena-distillery-admin-list'),
    path('create/', views.distillery_create, name='ena-distillery-create'),
    path('<int:pk>/', views.distillery_detail, name='ena-distillery-detail'),
    path('<int:pk>/update/', views.distillery_update, name='ena-distillery-update'),
    path('<int:pk>/delete/', views.distillery_delete, name='ena-distillery-delete'),
]

