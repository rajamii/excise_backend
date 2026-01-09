from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import HologramProcurementViewSet, HologramRequestViewSet

router = DefaultRouter()
router.register(r'procurement', HologramProcurementViewSet, basename='hologram-procurement')
router.register(r'request', HologramRequestViewSet, basename='hologram-request')

from .views import DailyHologramRegisterViewSet, HologramRollsDetailsViewSet
router.register(r'daily-register', DailyHologramRegisterViewSet, basename='daily-hologram-register')
router.register(r'rolls-details', HologramRollsDetailsViewSet, basename='hologram-rolls-details')

urlpatterns = [
    path('', include(router.urls)),
]
