from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

'''
    These are the urls that can be accessed by the frontend

'''

urlpatterns = [

    path('admin/', admin.site.urls),

    path('user/', include('user.urls')),

    path('masters/', include('masters.urls')),
    
    path('licenseapplication/', include('licenseapplication.urls')),

    path('salesman_barman/', include('salesman_barman.urls')),

    path('company_registration/', include('company_registration.urls')),

    path('contact_us/', include('contact_us.urls')),

    # captcha storage class required url pattern
    path('', include('captcha.urls'))

] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

