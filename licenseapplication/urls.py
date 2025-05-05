from django.conf import settings
from django.conf.urls.static import static
from django.urls import path
from .views import LicenseApplicationCreateView, LicenseApplicationListView, LicenseApplicationDetailView

urlpatterns = [
    # Endpoint to create a new license application (POST)
    path('apply/', LicenseApplicationCreateView.as_view(), name='license-application-create'),

    # Endpoint to list all license applications (GET)
    path('list/', LicenseApplicationListView.as_view(), name='license-application-list-all'),

    # Endpoint to get details of a specific license application by primary key (GET)
    path('detail/<int:pk>/', LicenseApplicationDetailView.as_view(), name='license-application-details'),
]

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
