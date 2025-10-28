 # models/transactional/urls.py
from django.urls import path, include

urlpatterns = [
    path('company-registration/', include(('models.transactional.company_registration.urls', 'company_registration'), namespace='company_registration')),
    path('license_application/', include(('models.transactional.license_application.urls', 'license_application'), namespace='license_application')),
    path('salesman_barman/', include(('models.transactional.salesman_barman.urls', 'salesman_barman'), namespace='salesman_barman')),
    path('transactiondata/', include(('models.transactional.transactiondata.urls', 'transactiondata'), namespace='transactiondata')),
    path('supply_chain/ena_requisition_details/', include(('models.transactional.supply_chain.ena_requisition_details.urls', 'ena_requisition_details'), namespace='ena_requisition_details')),
]
