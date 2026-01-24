from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import BrandWarehouseViewSet, BrandWarehouseUtilizationViewSet

# Create router and register viewsets
router = DefaultRouter()
router.register(r'brand-warehouse', BrandWarehouseViewSet, basename='brand-warehouse')
router.register(r'brand-warehouse-utilization', BrandWarehouseUtilizationViewSet, basename='brand-warehouse-utilization')

urlpatterns = [
    path('', include(router.urls)),
]
