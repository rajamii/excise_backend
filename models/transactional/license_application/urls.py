from django.conf import settings
from django.conf.urls.static import static
from django.urls import path, register_converter
from . import views


class EverythingConverter:
    regex = '.+'

    def to_python(self, value):
        return value

    def to_url(self, value):
        return value
    
register_converter(EverythingConverter, 'everything')

urlpatterns = [
    # Create a new license application (POST)
    path('apply/', views.create_license_application, name='license-application-create'),

    # List all license applications (GET)
    path('list/', views.list_license_applications, name='license-application-list-all'),

    # Retrieve details of a specific license application by its primary key (GET)
    path('detail/<everything:pk>/', views.license_application_detail, name='license-application-details'), 

    # Get dashboard statistics/counts (e.g., total applications, approved, pending, etc.) (GET)
    path('dashboard-counts/', views.dashboard_counts, name='dashboard-counts'),

    # List applications filtered by their current status (e.g., pending, approved, etc.) (GET)
    path('list-by-status/', views.application_group, name='applications-by-status'),

    path('location-fee/', views.get_location_fees, name='get-location-fees'),

    path('<everything:application_id>/print/', views.print_license_view, name='print-license'),

    # path('<everything:application_id>/next-stages/', get_next_stages, name='license-application-next-stages'),

    # Advance an application to the next stage in the workflow (e.g., review -> approval) (POST)
    # path('<everything:application_id>/advance/<int:stage_id>/', advance_license_application, name='advance-license-application'),
    
    # Level 2 site enquiry, allowing both GET and POST requests
    # path('<everything:application_id>/site-enquiry/', level2_site_enquiry, name='level2-site-enquiry'),

    # path('<everything:application_id>/raise-objection/', raise_objection, name='raise-objection'),

    # path('<everything:application_id>/objections/', get_objections, name='get-objections'),

    # path('<everything:application_id>/resolve-objections/', resolve_objections, name='resolve-objections'),

    # path('<everything:application_id>/delete/', delete_license_application, name='delete-application'),

    # path('<everything:application_id>/site-detail/', site_enquiry_detail, name='site-enquiry-detail'),

    # path('<everything:application_id>/pay-license-fee/', views.pay_license_fee, name="pay-licensee-fee"),
]

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
