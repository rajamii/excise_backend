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
    path('<int:state_code>/', views.state_detail, name='state-detail'),
    path('<int:state_code>/update/', views.state_update, name='state-update'),
    path('<int:state_code>/delete/', views.state_delete, name='state-delete'),
]

# District URLs
district_patterns = [
    path('', views.district_list, name='district-list'),
    path('create/', views.district_create, name='district-create'),
    path('<int:district_code>/', views.district_detail, name='district-detail'),
    path('<int:district_code>/update/', views.district_update, name='district-update'),
    path('<int:district_code>/delete/', views.district_delete, name='district-delete'),
]

# Subdivision URLs
subdivision_patterns = [
    path('', views.subdivision_list, name='subdivision-list'),
    path('create/', views.subdivision_create, name='subdivision-create'),
    path('<int:subdivision_code>/', views.subdivision_detail, name='subdivision-detail'),
    path('<int:subdivision_code>/update/', views.subdivision_update, name='subdivision-update'),
    path('<int:subdivision_code>/delete/', views.subdivision_delete, name='subdivision-delete'),
]

# Police Station URLs
policestation_patterns = [
    path('', views.policestation_list, name='policestation-list'),
    path('create/', views.policestation_create, name='policestation-create'),
    path('<int:policestation_code>/', views.policestation_detail, name='policestation-detail'),
    path('<int:policestation_code>/update/', views.policestation_update, name='policestation-update'),
    path('<int:policestation_code>/delete/', views.policestation_delete, name='policestation-delete'),
]

urlpatterns = [
    # Grouped patterns
    path('license-categories/', include(license_category_patterns)),
    path('license-types/', include(license_type_patterns)),
    path('states/', include(state_patterns)),
    path('districts/', include(district_patterns)),
    path('subdivisions/', include(subdivision_patterns)),
    path('police-stations/', include(policestation_patterns)),
]
