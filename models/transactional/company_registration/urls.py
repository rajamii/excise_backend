from django.urls import path, register_converter
from django.conf import settings
from django.conf.urls.static import static
from . import views


class EverythingConverter:
    regex = '.+'

    def to_python(self, value):
        return value

    def to_url(self, value):
        return value

register_converter(EverythingConverter, 'everything')

app_name = 'company_registration'

urlpatterns = [
    # Create a new company registration (POST)
    path('apply/', views.create_company_registration, name='apply'),

    # List all company registrations (GET)
    path('list/', views.list_company_registrations, name='list'),

    # Get dashboard statistics/counts (e.g., total applications, approved, pending, etc.) (GET)
    path('dashboard-counts/', views.dashboard_counts, name='dashboard-counts'),

    # List applications filtered by their current status (e.g., pending, approved, etc.) (GET)
    path('list-by-status/', views.application_group, name='applications-by-status'),

    # Pay company registration fee (POST) — MUST be before the greedy detail route
    path('pay-fee/<everything:application_id>/', views.pay_company_registration_fee, name='pay-company-registration-fee'),

    # Final license detail (GET)
    path('final-license/<everything:application_id>/', views.final_license_detail, name='final-license-detail'),

    # Final license QR code (GET)
    path('final-license/<everything:application_id>/qr-code/', views.final_license_qr_code, name='final-license-qr-code'),

    # Retrieve details of a specific company registration by application ID (GET)
    path('detail/<everything:application_id>/', views.company_registration_detail, name='detail'),
]

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
