from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'purposes', views.PurposeViewSet, basename='purpose')

urlpatterns = [
    path('', include(router.urls)),
]
