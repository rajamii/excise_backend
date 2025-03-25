from django.urls import path , include

from .views import (
    LicenseCategoryAPI,
    LicenseTypeAPI,
    SubDivisonApi,
    DistrictAPI,
    PoliceStationAPI,
)

from salesman_barman import urls as salesman_barman_urls
from registration_renewal import urls as registration_renewel_urls


urlpatterns = [
    # License Category URLs
    path('licensecategories/list/'             , LicenseCategoryAPI.as_view(), name='licensecategory-list'),
    path('licensecategories/detail/<int:id>/'  , LicenseCategoryAPI.as_view(), name='licensecategory-detail'),
    path('licensecategories/create/'           , LicenseCategoryAPI.as_view(), name='licensecategory-create'),
    path('licensecategories/update/<int:id>/'  , LicenseCategoryAPI.as_view(), name='licensecategory-update'),
    path('licensecategories/delete/<int:id>/'  , LicenseCategoryAPI.as_view(), name='licensecategory-delete'),

    # License Type URLs
    path('licensetypes/list/'                , LicenseTypeAPI.as_view(), name='licensetype-list'),
    path('licensetypes/detail/<int:id>/'     , LicenseTypeAPI.as_view(), name='licensetype-detail'),
    path('licensetypes/create/'              , LicenseTypeAPI.as_view(), name='licensetype-create'),
    path('licensetypes/update/<int:id>/'     , LicenseTypeAPI.as_view(), name='licensetype-update'),
    path('licensetypes/delete/<int:id>/'     , LicenseTypeAPI.as_view(), name='licensetype-delete'),

    # District URLs
    path('districts/list/'                  , DistrictAPI.as_view(), name='district-list'),
    path('districts/detail/<int:id>/'       , DistrictAPI.as_view(), name='district-detail'),
    path('districts/create/'                , DistrictAPI.as_view(), name='district-create'),
    path('districts/update/<int:id>/'       , DistrictAPI.as_view(), name='district-update'),
    path('districts/delete/<int:id>/'       , DistrictAPI.as_view(), name='district-delete'),

    # Subdivision URLs
    path('subdivisions/list/'                , SubDivisonApi.as_view(), name='subdivision-list'),
    path('subdivisions/detail/<int:id>/'     , SubDivisonApi.as_view(), name='subdivision-detail'),
    path('subdivisions/detail/<int:dc>/'     , SubDivisonApi.as_view(), name='subdivision-detail-by-code'),
    path('subdivisions/create/'              , SubDivisonApi.as_view(), name='subdivision-create'),
    path('subdivisions/update/<int:id>/'     , SubDivisonApi.as_view(), name='subdivision-update'),
    path('subdivisions/delete/<int:id>/'     , SubDivisonApi.as_view(), name='subdivision-delete'),

    # Police Station URLs
    path('policestations/list/'             , PoliceStationAPI.as_view(), name='policestation-list'),
    path('policestations/detail/<int:id>/'  , PoliceStationAPI.as_view(), name='policestation-detail'),
    path('policestations/create/'           , PoliceStationAPI.as_view(), name='policestation-create'),
    path('policestations/update/<int:id>/'  , PoliceStationAPI.as_view(), name='policestation-update'),
    path('policestations/delete/<int:id>/'  , PoliceStationAPI.as_view(), name='policestation-delete'),

    path('' ,include(salesman_barman_urls) ),
    path('' ,include(registration_renewel_urls)),

]
