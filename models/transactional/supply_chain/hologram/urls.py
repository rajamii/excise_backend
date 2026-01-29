from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    HologramProcurementViewSet, 
    HologramRequestViewSet,
    DailyHologramRegisterViewSet, 
    HologramRollsDetailsViewSet,
    HologramMonthlyReportViewSet,
    CommissionerDashboardViewSet
)

router = DefaultRouter()
router.register(r'procurement', HologramProcurementViewSet, basename='hologram-procurement')
router.register(r'request', HologramRequestViewSet, basename='hologram-request')
router.register(r'daily-register', DailyHologramRegisterViewSet, basename='daily-hologram-register')
router.register(r'rolls-details', HologramRollsDetailsViewSet, basename='hologram-rolls-details')
router.register(r'monthly-report', HologramMonthlyReportViewSet, basename='hologram-monthly-report')
router.register(r'commissioner-dashboard', CommissionerDashboardViewSet, basename='commissioner-dashboard')

urlpatterns = [
    path('', include(router.urls)),
]
