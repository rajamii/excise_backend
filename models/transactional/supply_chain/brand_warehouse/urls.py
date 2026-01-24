from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import BrandWarehouseViewSet, BrandWarehouseUtilizationViewSet, ProductionBatchViewSet

# Create router and register viewsets
router = DefaultRouter()
router.register(r'brand-warehouse', BrandWarehouseViewSet, basename='brand-warehouse')
router.register(r'brand-warehouse-utilization', BrandWarehouseUtilizationViewSet, basename='brand-warehouse-utilization')
router.register(r'production-batch', ProductionBatchViewSet, basename='production-batch')

urlpatterns = [
    path('', include(router.urls)),
]
