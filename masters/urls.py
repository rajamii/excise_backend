from django.urls import path
from . import views

urlpatterns = [
    # LicenseCategory API Endpoints
    path('license-categories-get-all/', views.LicenseCategoryList.as_view(), name='license-category-list'),  # GET for listing all license categories
    path('license-categories-get-one/<int:pk>/', views.LicenseCategoryDetail.as_view(), name='license-category-detail'),  # GET, PUT, DELETE for a specific license category

    # LicenseType API Endpoints
    path('license-type-get-all/', views.LicenseTypeList.as_view(), name='license-type-list'),  # GET for listing all license types
    path('license-type-get-one/<int:pk>/', views.LicenseTypeDetail.as_view(), name='license-type-detail'),  # GET for a specific license type
    path('license-type-update/<int:pk>/', views.LicenseTypeDetail.as_view(), name='license-type-update'),  # PUT for updating a specific license type
    path('license-type-delete/<int:pk>/', views.LicenseTypeDetail.as_view(), name='license-type-delete'),  # DELETE for deleting a specific license type

    # Subdivision API Endpoints
    path('subdivision-create/', views.SubDivisonApi.as_view(), name='subdivision-create'),  # POST for creating a subdivision
    path('subdivision-get-one/<int:pk>/', views.SubDivisonApi.as_view(), name='subdivision-detail'),  # GET for a specific subdivision
    path('subdivision-update/<int:pk>/', views.SubDivisonApi.as_view(), name='subdivision-update'),  # PUT for updating a specific subdivision
    path('subdivision-delete/<int:pk>/', views.SubDivisonApi.as_view(), name='subdivision-delete'),  # DELETE for deleting a specific subdivision

    # District API Endpoints
    path('district-create/', views.DistrictAdd.as_view(), name='district-create'),  # POST for creating a district
    path('district-update/<int:id>/', views.DistrictAdd.as_view(), name='district-update'),  # PUT for updating a district
    path('districts-get-all/', views.DistrictView.as_view(), name='district-list'),  # GET for listing all districts
    path('district-get-one/<int:pk>/', views.DistrictView.as_view(), name='district-detail'),  # GET for a specific district

    # PoliceStation API Endpoints
    path('policestation-create/', views.PoliceStationAPI.as_view(), name='policestation-create'),  # POST for creating a police station
    path('policestation-update/<int:id>/', views.PoliceStationAPI.as_view(), name='policestation-update'),  # PUT for updating a police station
    path('policestations-get-all/', views.PoliceStationAPI.as_view(), name='policestation-list'),  # GET for listing all police stations
    path('policestation-get-one/<int:pk>/', views.PoliceStationAPI.as_view(), name='policestation-detail'),  # GET for a specific police station
]

