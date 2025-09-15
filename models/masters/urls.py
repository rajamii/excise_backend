 # models/masters/urls.py
from django.urls import path, include

urlpatterns = [
    path('core/', include(('models.masters.core.urls', 'core_urls'), namespace='core_urls')),
    path('contact_us/', include(('models.masters.contact_us.urls', 'contact_us'), namespace='contact_us')),
    path('license/', include(('models.masters.license.urls', 'license'), namespace='license'))
]
