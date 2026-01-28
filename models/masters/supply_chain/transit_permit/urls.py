from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import TransitPermitBottleTypeViewSet, BrandMlInCasesViewSet

router = DefaultRouter()
router.register(r'bottle-types', TransitPermitBottleTypeViewSet, basename='transit-permit-bottle-types')
router.register(r'brand-ml-in-cases', BrandMlInCasesViewSet, basename='brand-ml-in-cases')

urlpatterns = [
    path('', include(router.urls)),
]
