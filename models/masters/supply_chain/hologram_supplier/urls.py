from django.urls import path

from . import views

urlpatterns = [
    path('',                 views.hologram_supplier_list,   name='hologram-supplier-list'),
    path('create/',          views.hologram_supplier_create, name='hologram-supplier-create'),
    path('<int:pk>/',        views.hologram_supplier_detail, name='hologram-supplier-detail'),
    path('<int:pk>/update/', views.hologram_supplier_update, name='hologram-supplier-update'),
    path('<int:pk>/delete/', views.hologram_supplier_delete, name='hologram-supplier-delete'),
]

