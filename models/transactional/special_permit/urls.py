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

app_name = 'special_permit'

urlpatterns = [
    path('eligible-licenses/', views.eligible_licenses, name='eligible-licenses'),
    path('apply/', views.create_special_permit_application, name='apply'),
    path('list/', views.list_special_permit_applications, name='list'),
    path('dashboard-counts/', views.dashboard_counts, name='dashboard-counts'),
    path('list-by-status/', views.application_group, name='applications-by-status'),
    path('detail/<everything:application_id>/', views.special_permit_detail, name='detail'),
    path('pay/<everything:application_id>/', views.pay_special_permit_fee_wallet, name='pay-fee-wallet'),
]

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
