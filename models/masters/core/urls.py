from django.urls import path
from . import views
from django.urls import include

app_name = 'core_masters'

# License Category URLs
license_category_patterns = [
    path('', views.license_category_list, name='license-category-list'),
    path('create/', views.license_category_create, name='license-category-create'),
    path('<int:pk>/', views.license_category_detail, name='license-category-detail'),
    path('<int:pk>/update/', views.license_category_update, name='license-category-update'),
    path('<int:pk>/delete/', views.license_category_delete, name='license-category-delete'),
]

# License Type URLs
license_type_patterns = [
    path('', views.license_type_list, name='license-type-list'),
    path('create/', views.license_type_create, name='license-type-create'),
    path('<int:pk>/', views.license_type_detail, name='license-type-detail'),
    path('<int:pk>/update/', views.license_type_update, name='license-type-update'),
    path('<int:pk>/delete/', views.license_type_delete, name='license-type-delete'),
]

# State URLs
state_patterns = [
    path('', views.state_list, name='state-list'),
    path('create/', views.state_create, name='state-create'),
    path('<int:pk>/', views.state_detail, name='state-detail'),
    path('<int:pk>/update/', views.state_update, name='state-update'),
    path('<int:pk>/delete/', views.state_delete, name='state-delete'),
]

# District URLs
district_patterns = [
    path('', views.district_list, name='district-list'),
    path('create/', views.district_create, name='district-create'),
    path('<int:pk>/', views.district_detail, name='district-detail'),
    path('<int:pk>/update/', views.district_update, name='district-update'),
    path('<int:pk>/delete/', views.district_delete, name='district-delete'),
]

# Subdivision URLs
subdivision_patterns = [
    path('', views.subdivision_list, name='subdivision-list'),
    path('create/', views.subdivision_create, name='subdivision-create'),
    path('<int:pk>/', views.subdivision_detail, name='subdivision-detail'),
    path('<int:pk>/update/', views.subdivision_update, name='subdivision-update'),
    path('<int:pk>/delete/', views.subdivision_delete, name='subdivision-delete'),
]

# Police Station URLs
policestation_patterns = [
    path('', views.policestation_list, name='policestation-list'),
    path('create/', views.policestation_create, name='policestation-create'),
    path('<int:pk>/', views.policestation_detail, name='policestation-detail'),
    path('<int:pk>/update/', views.policestation_update, name='policestation-update'),
    path('<int:pk>/delete/', views.policestation_delete, name='policestation-delete'),
]

# License Subcategory URLs
license_subcategory_patterns = [
    path('', views.license_subcategory_list, name='license-subcategory-list'),
    path('create/', views.license_subcategory_create, name='license-subcategory-create'),
    path('<int:pk>/', views.license_subcategory_detail, name='license-subcategory-detail'),
    path('<int:pk>/update/', views.license_subcategory_update, name='license-subcategory-update'),
    path('<int:pk>/delete/', views.license_subcategory_delete, name='license-subcategory-delete'),
]

# License Title URLs
license_title_patterns = [
    path('', views.license_title_list, name='license-title-list'),
    path('create/', views.license_title_create, name='license-title-create'),
    path('<int:pk>/', views.license_title_detail, name='license-title-detail'),
    path('<int:pk>/update/', views.license_title_update, name='license-title-update'),
    path('<int:pk>/delete/', views.license_title_delete, name='license-title-delete'),
]

# Road URLs
road_patterns = [
    path('', views.road_list, name='road-list'),
    path('create/', views.road_create, name='road-create'),
    path('<int:pk>/', views.road_detail, name='road-detail'),
    path('<int:pk>/update/', views.road_update, name='road-update'),
    path('<int:pk>/delete/', views.road_delete, name='road-delete'),
]

urlpatterns = [
    # Grouped patterns
    path('license-categories/', include(license_category_patterns)),
    path('license-types/', include(license_type_patterns)),
    path('states/', include(state_patterns)),
    path('districts/', include(district_patterns)),
    path('subdivisions/', include(subdivision_patterns)),
    path('police-stations/', include(policestation_patterns)),
    path('license-subcategories/', include(license_subcategory_patterns)),
    path('license-titles/', include(license_title_patterns)),
    path('roads/', include(road_patterns)),
]
