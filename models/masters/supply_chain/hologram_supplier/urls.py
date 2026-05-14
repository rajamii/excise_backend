from django.urls import path

from . import views

urlpatterns = [
    path('', views.MasterHologramSupplierListAPIView.as_view(), name='master-hologram-supplier-list'),
]

