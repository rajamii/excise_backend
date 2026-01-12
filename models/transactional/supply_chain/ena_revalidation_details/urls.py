from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import EnaRevalidationDetailViewSet

router = DefaultRouter()
router.register(r'', EnaRevalidationDetailViewSet)

urlpatterns = [
    path('', include(router.urls)),
]
