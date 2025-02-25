from django.urls import path
from . import views

urlpatterns = [
    path('license-categories/', views.LicenseCategoryList.as_view(), name='license-category-list'),
    path('license-type/', views.LicenseTypeList.as_view(), name='license-type-list'),
    path('subdivision/', views.SubDivisonApi.as_view(), name='subdivision-create'),  # POST for creating a subdivision
    path('subdivision/<int:pk>/', views.SubDivisonApi.as_view(), name='subdivision-detail'),  # GET, PUT for a specific subdivision

    # District API Endpoints
    path('district/', views.DistrictAdd.as_view(), name='district-create'),  # POST for creating a district
    path('district/<int:id>/', views.DistrictAdd.as_view(), name='district-update'),  # PUT for updating a district
    path('districts/', views.DistrictView.as_view(), name='district-list'),  # GET for listing all districts
    path('districts/<int:pk>/', views.DistrictView.as_view(), name='district-detail'),  # GET for a specific district

    # PoliceStation API Endpoints
    path('policestation/', views.PoliceStationAPI.as_view(), name='policestation-create'),  # POST for creating a police stationp
    path('policestation/<int:id>/', views.PoliceStationAPI.as_view(), name='policestation-update'),  # PUT for updating a police station
    path('policestations/', views.PoliceStationAPI.as_view(), name='policestation-list'),  # GET for listing all police stations
    path('policestations/<int:pk>/', views.PoliceStationAPI.as_view(), name='policestation-detail'),  
]