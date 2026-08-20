from django.urls import path, register_converter

from . import views


class EverythingConverter:
    regex = '.+'

    def to_python(self, value):
        return value

    def to_url(self, value):
        return value


register_converter(EverythingConverter, 'everything')

app_name = 'distributor_permit'

urlpatterns = [
    path('', views.DistributorPermitListCreateView.as_view(), name='list-create'),
    path('suppliers/', views.DistributorPermitSuppliersView.as_view(), name='suppliers'),
    path('brand-master/', views.DistributorPermitBrandMasterView.as_view(), name='brand-master'),
    path('premises/', views.DistributorPermitPremisesView.as_view(), name='premises'),
    path('<everything:reference_no>/', views.DistributorPermitDetailView.as_view(), name='detail'),
    path('<everything:reference_no>/perform-action/', views.DistributorPermitPerformActionView.as_view(), name='perform-action'),
    path('<everything:reference_no>/documents/', views.DistributorPermitDocumentUploadView.as_view(), name='documents'),
]
