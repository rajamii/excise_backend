from rest_framework.routers import DefaultRouter

from .views import BrandWarehouseUtilizationViewSet


router = DefaultRouter()
# Empty prefix so list endpoint becomes `/brand-warehouse-utilization/`
router.register(r'', BrandWarehouseUtilizationViewSet, basename='brand-warehouse-utilization-short')

urlpatterns = router.urls

