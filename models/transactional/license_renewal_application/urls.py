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

    # Dashboard counts + grouping (same shape as new_license_application)
    path('dashboard-counts/', views.dashboard_counts, name='dashboard-counts'),
    path('list-by-status/', views.application_group, name='applications-by-status'),

    # Initiate renewal tracking application (LRA/...)
    path('renew/<everything:license_id>/', views.initiate_renewal, name='renew'),

    # Wallet fee payments (post-commissioner approval)
    path('<everything:application_id>/pay-license-fee/', views.pay_license_fee_wallet, name='pay-license-fee-wallet'),
    path('<everything:application_id>/pay-security-fee/', views.pay_security_fee_wallet, name='pay-security-fee-wallet'),
]

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
