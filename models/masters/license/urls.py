from django.urls import path, re_path
from .views import list_licenses, license_detail, active_licensees

urlpatterns = [
    # Endpoint to list all licenses (GET)
    path('list/', list_licenses, name='license-list-all'),

    path('active/', active_licensees, name='active-licensees'),
    
    # Endpoint to retrieve details of a specific license by its license_id (GET)
    re_path(r'detail/(?P<license_id>.+)/$', license_detail, name='license-details'),
]