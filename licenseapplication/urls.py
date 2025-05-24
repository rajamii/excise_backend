from django.conf import settings
from django.conf.urls.static import static
from django.urls import path
from .views import LicenseApplicationCreateView, LicenseApplicationListView, LicenseApplicationDetailView, LicenseApplicationUpdateView, LicenseApplicationDeleteView, DashboardCountsView, ApplicationListView, LicenseApplicationAdvanceView

urlpatterns = [
    # Endpoint to create a new license application (POST)
    path('apply/', LicenseApplicationCreateView.as_view(), name='license-application-create'),

    # Endpoint to list all license applications (GET)
    path('list/', LicenseApplicationListView.as_view(), name='license-application-list-all'),

    # Endpoint to retrieve details of a specific license application by its primary key (GET)
    path('detail/<int:pk>/', LicenseApplicationDetailView.as_view(), name='license-application-details'),

    # Endpoint to update a specific license application by its primary key (PUT/PATCH)
    path('<int:pk>/update/', LicenseApplicationUpdateView.as_view(), name='license-application-update'),

    path('<int:pk>/delete/', LicenseApplicationDeleteView.as_view(), name='license-application-delete'),

    # Endpoint to get dashboard statistics/counts (e.g., total applications, approved, pending, etc.) (GET)
    path('dashboard-counts/', DashboardCountsView.as_view(), name='dashboard-counts'),

    # Endpoint to list applications filtered by their current status (e.g., pending, approved, etc.) (GET)
    path('list-by-status/', ApplicationListView.as_view(), name='applications-by-status'),

    # Endpoint to advance an application to the next stage in the workflow (e.g., review -> approval) (POST)
    path('<int:pk>/advance/', LicenseApplicationAdvanceView.as_view(), name='license-application-advance'),
]


urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
