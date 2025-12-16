# yourapp/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'', views.TransitPermitDistributorDataViewSet, basename='transit-permit-distributor-data')

urlpatterns = [
    # main router (list/detail/search)
    path('', include(router.urls)),
]
