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
    path('apply/', views.create_new_license_application, name='new-license-apply'),

    # List all license applications (GET)
    path('list/', views.list_license_applications, name='new-license-list-all'),

    # Retrieve details of a specific license application by its primary key (GET)
    path('detail/<everything:pk>/', views.license_application_detail, name='license-application-details'),

    # Final license data for UI/printing (GET)
    path('final-license/<everything:application_id>/', views.final_license_detail, name='final-license-detail'),
    path('final-license/<everything:application_id>/passport-photo/', views.final_license_passport_photo, name='final-license-passport-photo'),
    path('final-license/<everything:application_id>/qr-code/', views.final_license_qr_code, name='final-license-qr-code'),

    # Get dashboard statistics/counts (e.g., total applications, approved, pending, etc.) (GET)
    path('dashboard-counts/', views.dashboard_counts, name='dashboard-counts'),

    # List applications filtered by their current status (e.g., pending, approved, etc.) (GET)
    path('list-by-status/', views.application_group, name='applications-by-status'),

    path('renew/<everything:license_id>/', views.initiate_renewal, name='renew'),

    # Print License
    path('<everything:application_id>/print/', views.print_license_view, name='print-license'),
]
