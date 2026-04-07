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
    
    path('list/', views.list_licenses, name='license-list-all'),

    path('active/', views.active_licensees, name='active-licensees'),
    
    path('detail/<everything:license_id>/', views.license_detail, name='license-details'),

    # Site Admin: Terms & Conditions editor (legacy code keyed)
    path('form-terms/', views.master_license_form_terms, name='master-license-form-terms'),
    path('form-terms/update/', views.master_license_form_terms_update, name='master-license-form-terms-update'),

    path('<everything:license_id>/print/', views.print_license_view, name='print-license'),

    path('<everything:license_id>/pay-print-fee/', views.pay_print_fee_view, name='pay-print-fee'),

    path('me/', views.MyLicensesListView.as_view(), name='my-licenses-list'),
]
