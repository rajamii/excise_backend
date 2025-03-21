from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import SalesmanBarmanDetailsViewSet, DocumentsDetailsViewSet

router = DefaultRouter()
router.register(r'salesman_barman_details', SalesmanBarmanDetailsViewSet)
urlpatterns = [
    path('api/', include(router.urls)),
]
