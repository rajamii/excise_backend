from django.urls import path, register_converter

from . import views


class EverythingConverter:
    regex = '.+'

    def to_python(self, value):
        return value

    def to_url(self, value):
        return value


register_converter(EverythingConverter, 'everything')

from rest_framework.routers import DefaultRouter

router = DefaultRouter()
router.register(r'revalidation-schedules', views.IMFLRevalidationActivationScheduleViewSet, basename='revalidation-schedules')
router.register(r'revalidation', views.IMFLRevalidationViewSet, basename='revalidation')
router.register(r'cancellation', views.IMFLCancellationViewSet, basename='cancellation')

app_name = 'distributor_permit'

urlpatterns = [
    path('', views.DistributorPermitListCreateView.as_view(), name='list-create'),
    path('dashboard-counts/', views.dashboard_counts, name='dashboard-counts'),
    path('suppliers/', views.DistributorPermitSuppliersView.as_view(), name='suppliers'),
    path('brand-master/', views.DistributorPermitBrandMasterView.as_view(), name='brand-master'),
    path('premises/', views.DistributorPermitPremisesView.as_view(), name='premises'),
    path('cancellation/<everything:reference_no>/perform_action/', views.DistributorPermitPerformActionView.as_view(), name='cancellation-perform-action-1'),
    path('cancellation/<everything:reference_no>/perform-action/', views.DistributorPermitPerformActionView.as_view(), name='cancellation-perform-action-2'),
    path('revalidation/<everything:reference_no>/perform_action/', views.DistributorPermitPerformActionView.as_view(), name='revalidation-perform-action-1'),
    path('revalidation/<everything:reference_no>/perform-action/', views.DistributorPermitPerformActionView.as_view(), name='revalidation-perform-action-2'),
] + router.urls + [
    path('<everything:reference_no>/perform_action/', views.DistributorPermitPerformActionView.as_view(), name='perform-action-underscore'),
    path('<everything:reference_no>/perform-action/', views.DistributorPermitPerformActionView.as_view(), name='perform-action'),
    path('<everything:reference_no>/documents/', views.DistributorPermitDocumentUploadView.as_view(), name='documents'),
    path('<everything:reference_no>/', views.DistributorPermitDetailView.as_view(), name='detail'),
]
