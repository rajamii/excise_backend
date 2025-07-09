 # models/masters/urls.py
from django.urls import path, include

urlpatterns = [
    path('company-registration/', include(('models.masters.company_registration.urls', 'company_registration'), namespace='company_registration')),
    path('core/', include(('models.masters.core.urls', 'core_urls'), namespace='core_urls')),
    path('license_application/', include(('models.masters.license_application.urls', 'license_application'), namespace='license_application')),
    path('salesman_barman/', include(('models.masters.salesman_barman.urls', 'salesman_barman'), namespace='salesman_barman')),
    path('contact_us/', include(('models.masters.contact_us.urls', 'contact_us'), namespace='contact_us')),
]
