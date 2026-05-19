from django.urls import path
from . import views

app_name = 'bulk_spirit'

urlpatterns = [
    path('bulk-spirit-types/', views.BulkSpiritTypeListAPIView.as_view(), name='bulk-spirit-types-list'),
    # Site admin CRUD
    path('bulk-spirit-types-admin/', views.bulk_spirit_type_admin_list, name='bulk-spirit-types-admin-list'),
    path('bulk-spirit-types/create/', views.bulk_spirit_type_create, name='bulk-spirit-types-create'),
    path('bulk-spirit-types/<int:pk>/', views.bulk_spirit_type_detail, name='bulk-spirit-types-detail'),
    path('bulk-spirit-types/<int:pk>/update/', views.bulk_spirit_type_update, name='bulk-spirit-types-update'),
    path('bulk-spirit-types/<int:pk>/delete/', views.bulk_spirit_type_delete, name='bulk-spirit-types-delete'),
]
