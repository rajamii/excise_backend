from rest_framework.routers import DefaultRouter

from .views import BrandWarehouseViewSet


router = DefaultRouter()
# Empty prefix so list endpoint becomes `/brand-warehouse/`
router.register(r'', BrandWarehouseViewSet, basename='brand-warehouse-short')

urlpatterns = router.urls

