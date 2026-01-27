from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import TransitPermitBottleTypeViewSet

router = DefaultRouter()
router.register(r'bottle-types', TransitPermitBottleTypeViewSet, basename='transit-permit-bottle-types')

urlpatterns = [
    path('', include(router.urls)),
]
