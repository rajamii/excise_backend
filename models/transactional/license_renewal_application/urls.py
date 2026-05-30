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
]

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
