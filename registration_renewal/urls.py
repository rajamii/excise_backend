from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import CompanyDetailsViewSet, MemberDetailsViewSet, DocumentDetailsViewSet

# Create a router and register viewsets
router = DefaultRouter()
router.register(r'companies', CompanyDetailsViewSet)
router.register(r'members', MemberDetailsViewSet)
router.register(r'documents', DocumentDetailsViewSet)

urlpatterns = [
    
    path('api/', include(router.urls)),  # Include DRF router URLs
]
