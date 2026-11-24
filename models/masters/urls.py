 # models/masters/urls.py
from django.urls import path, include
from models.masters.core import views as core_views

urlpatterns = [
    path('core/', include(('models.masters.core.urls', 'core_urls'), namespace='core_urls')),
    path('districts/<str:identifier>/site-enquiry-officers/', core_views.district_site_enquiry_officers, name='short-district-site-enquiry-officers'),
    path('site-enquiry-stages/', core_views.site_enquiry_stage_config_list, name='short-site-enquiry-stages'),
    path('site-enquiry-stages/<str:identifier>/', core_views.site_enquiry_stage_config_update, name='short-site-enquiry-stages-update'),
    path('contact_us/', include(('models.masters.contact_us.urls', 'contact_us'), namespace='contact_us')),
    path('about_us/', include(('models.masters.about_us.urls', 'about_us'), namespace='about_us')),
    path('preventive_raids/', include(('models.masters.preventive_raids.urls', 'preventive_raids'), namespace='preventive_raids')),
    path('license/', include(('models.masters.license.urls', 'license'), namespace='license')),
    path('supply_chain/', include(('models.masters.supply_chain.urls', 'supply_chain_masters'), namespace='supply_chain_masters')),
    path('company-collaboration/', include(('models.masters.company_collaboration.urls', 'masters_company_collaboration'), namespace='masters_company_collaboration')),
]

