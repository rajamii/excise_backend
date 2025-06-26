from django.conf import settings
from django.conf.urls.static import static
from django.urls import path
from django.urls import re_path
from .views import (
    create_license_application,
    list_license_applications,
    license_application_detail,
    advance_license_application,
    level2_site_enquiry,
    dashboard_counts,
    application_group,
    get_location_fees,
    get_objections,
    resolve_objections,
    print_license_view,
    delete_license_application,
    site_enquiry_detail
)

urlpatterns = [
    # Endpoint to create a new license application (POST)
    path('apply/', create_license_application, name='license-application-create'),

    # Endpoint to list all license applications (GET)
    path('list/', list_license_applications, name='license-application-list-all'),

    # Endpoint to retrieve details of a specific license application by its primary key (GET)
    path('detail/<int:pk>/', license_application_detail, name='license-application-details'),

    # Endpoint to update a specific license application by its primary key (PUT/PATCH)
    # path('<int:pk>/update/', LicenseApplicationUpdateView.as_view(), name='license-application-update'),

    # path('<int:pk>/delete/', LicenseApplicationDeleteView.as_view(), name='license-application-delete'),

    # Endpoint to get dashboard statistics/counts (e.g., total applications, approved, pending, etc.) (GET)
    path('dashboard-counts/', dashboard_counts, name='dashboard-counts'),

    # Endpoint to list applications filtered by their current status (e.g., pending, approved, etc.) (GET)
    path('list-by-status/', application_group, name='applications-by-status'),

    # Endpoint to advance an application to the next stage in the workflow (e.g., review -> approval) (POST)
    re_path(r'(?P<application_id>.+)/advance/$', advance_license_application, name='advance-license-application'),
    
    # Endpoint for Level 2 site enquiry, allowing both GET and POST requests
    re_path(r'(?P<application_id>.+)/site-enquiry/$', level2_site_enquiry, name='level2-site-enquiry'),

    path('location-fee/', get_location_fees, name='get_location_fees'),

    re_path(r'(?P<application_id>.+)/objections/$', get_objections, name='get_objections'),

    re_path(r'(?P<application_id>.+)/resolve-objections/$', resolve_objections, name='resolve_objections'),

    re_path(r'(?P<application_id>.+)/print/$', print_license_view, name='print_license'),

    re_path(r'(?P<application_id>.+)/delete/$', delete_license_application, name='delete_application'),

    re_path(r'(?P<application_id>.+)/site-detail/$', site_enquiry_detail, name='site_enquiry_detail'),
]

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
