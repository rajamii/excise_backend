 # models/transactional/urls.py
from django.urls import path, include

urlpatterns = [
    path('company_registration/', include(('models.transactional.company_registration.urls', 'company_registration'), namespace='company_registration')),
    path('license_application/', include(('models.transactional.license_application.urls', 'license_application'), namespace='license_application')),
    path('salesman_barman/', include(('models.transactional.salesman_barman.urls', 'salesman_barman'), namespace='salesman_barman')),
    path('site_enquiry/', include(('models.transactional.site_enquiry.urls', 'site_enquiry'), namespace='site_enquiry')),
    path('new_license_application/', include(('models.transactional.new_license_application.urls', 'new_license_application'), namespace='new_license_application')),
]
