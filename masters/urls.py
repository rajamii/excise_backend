from django.urls import path, include
from .views import (
    LicenseCategoryAPI,
    LicenseTypeAPI,
    SubdivisionApi,
    DistrictAPI,
    PoliceStationAPI,
    LicenseSubcategoryAPI,
    RoadAPI,
    LicenseTitleAPI,
)

urlpatterns = [
    # License Category URLs
    path('licensecategories/list/', LicenseCategoryAPI.as_view(), name='licensecategory-list'),
    path('licensecategories/detail/<int:id>/', LicenseCategoryAPI.as_view(), name='licensecategory-detail'),
    path('licensecategories/create/', LicenseCategoryAPI.as_view(), name='licensecategory-create'),
    path('licensecategories/update/<int:id>/', LicenseCategoryAPI.as_view(), name='licensecategory-update'),
    path('licensecategories/delete/<int:id>/', LicenseCategoryAPI.as_view(), name='licensecategory-delete'),

    # License Type URLs
    path('licensetypes/list/', LicenseTypeAPI.as_view(), name='licensetype-list'),
    path('licensetypes/detail/<int:id>/', LicenseTypeAPI.as_view(), name='licensetype-detail'),
    path('licensetypes/create/', LicenseTypeAPI.as_view(), name='licensetype-create'),
    path('licensetypes/update/<int:id>/', LicenseTypeAPI.as_view(), name='licensetype-update'),
    path('licensetypes/delete/<int:id>/', LicenseTypeAPI.as_view(), name='licensetype-delete'),

    # District URLs
    path('districts/list/', DistrictAPI.as_view(), name='district-list'),
    path('districts/detail/<int:id>/', DistrictAPI.as_view(), name='district-detail'),
    path('districts/create/', DistrictAPI.as_view(), name='district-create'),
    path('districts/update/<int:id>/', DistrictAPI.as_view(), name='district-update'),
    path('districts/delete/<int:id>/', DistrictAPI.as_view(), name='district-delete'),

    # Subdivision URLs
    path('subdivisions/list/', SubdivisionApi.as_view(), name='subdivision-list'),
    path('subdivisions/detail/<int:id>/', SubdivisionApi.as_view(), name='subdivision-detail'),
    path('subdivisions/detail/<int:dc>/', SubdivisionApi.as_view(), name='subdivision-detail-by-code'),
    path('subdivisions/create/', SubdivisionApi.as_view(), name='subdivision-create'),
    path('subdivisions/update/<int:id>/', SubdivisionApi.as_view(), name='subdivision-update'),
    path('subdivisions/delete/<int:id>/', SubdivisionApi.as_view(), name='subdivision-delete'),

    # Police Station URLs
    path('policestations/list/', PoliceStationAPI.as_view(), name='policestation-list'),
    path('policestations/detail/<int:id>/', PoliceStationAPI.as_view(), name='policestation-detail'),
    path('policestations/create/', PoliceStationAPI.as_view(), name='policestation-create'),
    path('policestations/update/<int:id>/', PoliceStationAPI.as_view(), name='policestation-update'),
    path('policestations/delete/<int:id>/', PoliceStationAPI.as_view(), name='policestation-delete'),

    # License Subcategory URLs
    path('license-subcategories/list/', LicenseSubcategoryAPI.as_view(), name='license-subcategory-list'),
    path('license-subcategories/detail/<int:id>/', LicenseSubcategoryAPI.as_view(), name='license-subcategory-detail'),
    path('license-subcategories/create/', LicenseSubcategoryAPI.as_view(), name='license-subcategory-create'),
    path('license-subcategories/update/<int:id>/', LicenseSubcategoryAPI.as_view(), name='license-subcategory-update'),
    path('license-subcategories/delete/<int:id>/', LicenseSubcategoryAPI.as_view(), name='license-subcategory-delete'),

    # License Title URLs
    path('licensetitles/list/', LicenseTitleAPI.as_view(), name='licensetitle-list'),
    path('licensetitles/detail/<int:id>/', LicenseTitleAPI.as_view(), name='licensetitle-detail'),
    path('licensetitles/create/', LicenseTitleAPI.as_view(), name='licensetitle-create'),
    path('licensetitles/update/<int:id>/', LicenseTitleAPI.as_view(), name='licensetitle-update'),
    path('licensetitles/delete/<int:id>/', LicenseTitleAPI.as_view(), name='licensetitle-delete'),

    # Road URLs
    path('roads/list/', RoadAPI.as_view(), name='road-list'),
    path('roads/detail/<int:id>/', RoadAPI.as_view(), name='road-detail'),
    path('roads/create/', RoadAPI.as_view(), name='road-create'),
    path('roads/update/<int:id>/', RoadAPI.as_view(), name='road-update'),
    path('roads/delete/<int:id>/', RoadAPI.as_view(), name='road-delete'),
]