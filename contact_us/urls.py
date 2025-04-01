from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import NodalOfficerViewSet, PublicInformationOfficerViewSet, DirectorateAndDistrictOfficialsViewSet, GrievanceRedressalOfficerViewSet

router = DefaultRouter()
router.register(r'nodal-officer', NodalOfficerViewSet)
router.register(r'public-information-officer', PublicInformationOfficerViewSet)
router.register(r'directorate-and-district-officials', DirectorateAndDistrictOfficialsViewSet)
router.register(r'grievance-redressal-officer', GrievanceRedressalOfficerViewSet)

urlpatterns = [
    path('api/', include(router.urls)),
]
