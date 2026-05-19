from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'purposes', views.PurposeViewSet, basename='purpose')

urlpatterns = [
    path('', include(router.urls)),
    # Site admin CRUD (prefixed with 'admin/' to avoid clash with the router)
    path('admin/purposes/', views.purpose_admin_list, name='purpose-admin-list'),
    path('admin/purposes/create/', views.purpose_create, name='purpose-create'),
    path('admin/purposes/<int:pk>/', views.purpose_detail, name='purpose-detail'),
    path('admin/purposes/<int:pk>/update/', views.purpose_update, name='purpose-update'),
    path('admin/purposes/<int:pk>/delete/', views.purpose_delete, name='purpose-delete'),
    path('admin/purposes/<int:pk>/toggle-active/', views.purpose_toggle_active, name='purpose-toggle-active'),
]
