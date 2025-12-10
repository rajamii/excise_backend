from django.conf import settings
from django.conf.urls.static import static
from django.urls import path, register_converter
from .views import (
    create_license_application,
    list_license_applications,
    license_application_detail,
    advance_license_application,
    dashboard_counts,
    application_group,
    get_location_fees,
    raise_objection,
    get_objections,
    resolve_objections,
    print_license_view,
    delete_license_application,
    pay_license_fee,
    get_next_stages,
)

class EverythingConverter:
    regex = '.+'

    def to_python(self, value):
        return value

    def to_url(self, value):
        return value
    
register_converter(EverythingConverter, 'everything')

urlpatterns = [
    # Create a new license application (POST)
    path('apply/', create_license_application, name='license-application-create'),

    # List all license applications (GET)
    path('list/', list_license_applications, name='license-application-list-all'),

    # Retrieve details of a specific license application by its primary key (GET)
    path('detail/<everything:pk>/', license_application_detail, name='license-application-details'), 

    # Get dashboard statistics/counts (e.g., total applications, approved, pending, etc.) (GET)
    path('dashboard-counts/', dashboard_counts, name='dashboard-counts'),

    # List applications filtered by their current status (e.g., pending, approved, etc.) (GET)
    path('list-by-status/', application_group, name='applications-by-status'),

    path('<everything:application_id>/next-stages/', get_next_stages, name='license-application-next-stages'),

    # Advance an application to the next stage in the workflow (e.g., review -> approval) (POST)
    path('<everything:application_id>/advance/<int:stage_id>/', advance_license_application, name='advance-license-application'),
    
    # Level 2 site enquiry, allowing both GET and POST requests
    # path('<everything:application_id>/site-enquiry/', level2_site_enquiry, name='level2-site-enquiry'),

    path('location-fee/', get_location_fees, name='get-location-fees'),

    path('<everything:application_id>/raise-objection/', raise_objection, name='raise-objection'),

    path('<everything:application_id>/objections/', get_objections, name='get-objections'),

    path('<everything:application_id>/resolve-objections/', resolve_objections, name='resolve-objections'),

    path('<everything:application_id>/print/', print_license_view, name='print-license'),

    path('<everything:application_id>/delete/', delete_license_application, name='delete-application'),

    # path('<everything:application_id>/site-detail/', site_enquiry_detail, name='site-enquiry-detail'),

    path('<everything:application_id>/pay-license-fee/', pay_license_fee, name="pay-licensee-fee"),
]

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
