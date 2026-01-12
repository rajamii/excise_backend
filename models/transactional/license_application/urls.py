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

    path('renew/<everything:license_id>/', views.initiate_renewal, name='initiate-renewal'),
]

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
