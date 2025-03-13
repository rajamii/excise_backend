from django.urls import path
from . import views

urlpatterns = [
    path('license-categories/', views.LicenseCategoryList.as_view(), name='license-category-list'),
    path('license-categories/<int:pk>/', views.LicenseCategoryDetail.as_view(), name='license-category-detail'),  # GET, PUT, DELETE
    path('license-type/', views.LicenseTypeList.as_view(), name='license-type-list'),

    path('license-types/<int:pk>/', views.LicenseTypeDetail.as_view(), name='license-type-detail'),  # GET, PUT, DELETE   

    path('subdivision/', views.SubDivisonApi.as_view(), name='subdivision-create'),  # POST for creating a subdivision
    path('subdivision/<int:pk>/', views.SubDivisonApi.as_view(), name='subdivision-detail'),  # GET, PUT for a specific subdivision


    # POST for creating a subdivision

    path('subdivision/', views.SubDivisonApi.as_view(), name='subdivision-create'),

    # GET, PUT for a specific subdivision

    path('subdivision/<int:pk>/', views.SubDivisonApi.as_view(), name='subdivision-detail'), 



    ### District API Endpoints ###

    # POST for creating a district

    path('district/', views.DistrictAdd.as_view(), name='district-create'),

    # PUT for updating a district

    path('district/<int:id>/', views.DistrictAdd.as_view(), name='district-update'),

    # GET for listing all districts      

    path('districts/', views.DistrictView.as_view(), name='district-list'),

    # GET for a specific district

    path('districts/<int:pk>/', views.DistrictView.as_view(), name='district-detail'),  


    ### PoliceStation API Endpoints ###

    # POST for creating a police station
    
    path('policestation/', views.PoliceStationAPI.as_view(), name='policestation-create'),

    # PUT for updating a police station

    path('policestation/<int:id>/', views.PoliceStationAPI.as_view(), name='policestation-update'),

    # GET for listing all police stations
    
    path('policestations/', views.PoliceStationAPI.as_view(), name='policestation-list'),
     
    path('policestations/<int:pk>/', views.PoliceStationAPI.as_view(), name='policestation-detail'),  
]
