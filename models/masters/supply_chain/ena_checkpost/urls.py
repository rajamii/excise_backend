from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'checkposts', views.CheckpostViewSet, basename='checkpost')

urlpatterns = [
    path('', include(router.urls)),
    # Site admin CRUD (prefixed with 'admin/' to avoid clash with the router)
    path('admin/checkposts/', views.checkpost_admin_list, name='checkpost-admin-list'),
    path('admin/checkposts/create/', views.checkpost_create, name='checkpost-create'),
    path('admin/checkposts/<int:pk>/', views.checkpost_detail, name='checkpost-detail'),
    path('admin/checkposts/<int:pk>/update/', views.checkpost_update, name='checkpost-update'),
    path('admin/checkposts/<int:pk>/delete/', views.checkpost_delete, name='checkpost-delete'),
    path('admin/checkposts/<int:pk>/toggle-active/', views.checkpost_toggle_active, name='checkpost-toggle-active'),
]
