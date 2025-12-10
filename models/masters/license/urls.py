from django.urls import path, register_converter
from .views import list_licenses, license_detail, active_licensees

class EverythingConverter:
    regex = '.+'

    def to_python(self, value):
        return value

    def to_url(self, value):
        return value
    
register_converter(EverythingConverter, 'everything')


urlpatterns = [
    # Endpoint to list all licenses (GET)
    path('list/', list_licenses, name='license-list-all'),

    path('active/', active_licensees, name='active-licensees'),
    
    path('detail/<everything:license_id>/', license_detail, name='license-details'),
]