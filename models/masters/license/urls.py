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

    path('<everything:license_id>/print/', views.print_license_view, name='print-license'),
]