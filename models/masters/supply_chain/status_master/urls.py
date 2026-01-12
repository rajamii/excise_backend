from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import StatusMasterViewSet

router = DefaultRouter()
router.register(r'status-master', StatusMasterViewSet)

urlpatterns = [
    path('', include(router.urls)),
]
