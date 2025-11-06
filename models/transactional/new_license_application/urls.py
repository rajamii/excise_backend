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

    # Get dashboard statistics/counts (e.g., total applications, approved, pending, etc.) (GET)
    path('dashboard-counts/', views.dashboard_counts, name='dashboard-counts'),

    # List applications filtered by their current status (e.g., pending, approved, etc.) (GET)
    path('list-by-status/', views.application_group, name='applications-by-status'),

    # Get Next Stages
    path('<everything:application_id>/next-stages/', views.get_next_stages, name='license-application-next-stages'),

    # Advance an application to the next stage in the workflow (e.g., review -> approval) (POST)
    path('<everything:application_id>/advance/<int:stage_id>/', views.advance_license_application, name='advance-license-application'),

    # Raise Objection
    path('<everything:application_id>/raise-objection/', views.raise_objection, name='raise-objection'),

    # Get Objections
    path('<everything:application_id>/objections/', views.get_objections, name='get-objections'),

    # Resolve Objections
    path('<everything:application_id>/resolve-objections/', views.resolve_objections, name='resolve-objections'),

    # Print License
    path('<everything:application_id>/print/', views.print_license_view, name='print-license'),

    # Pay License Fee
    path('<everything:application_id>/pay-license-fee/', views.pay_license_fee, name="pay-licensee-fee"),
]