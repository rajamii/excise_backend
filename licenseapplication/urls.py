from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import LicenseApplicationViewSet

router = DefaultRouter()
router.register(r'license-applications', LicenseApplicationViewSet)

urlpatterns = [
    path('', include(router.urls)),
]
