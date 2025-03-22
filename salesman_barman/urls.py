from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import SalesmanBarmanDetailsViewSet, DocumentsDetailsViewSet

router = DefaultRouter()
router.register(r'salesman-barman', SalesmanBarmanDetailsViewSet, basename='salesman-barman')
router.register(r'salesman-barman/documents', DocumentsDetailsViewSet, basename='documents')

urlpatterns = [
    path('', include(router.urls)),
]
