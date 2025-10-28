from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'ena-cancellation-details', views.EnaCancellationDetailViewSet, basename='enacancellationdetail')

urlpatterns = [
    path('', include(router.urls)),
]
