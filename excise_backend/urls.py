from django.contrib import admin
from django.urls import path, re_path
from django.conf import settings
from django.conf.urls.static import static
from django.urls import include 

from models.transactional.public_validation import views as public_validation_views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('auth/', include('auth.urls')),
    # Short alias routes (keep existing long routes too)
    path('', include('excise_backend.shortcuts_urls')),

    # Public validation (also exposed under /masters/ for deployments that proxy only /masters/ to Django)
    re_path(r'^masters/v/(?P<code>.+)/$', public_validation_views.validate_license_landing, name='validate-license-masters'),
    path('masters/', include('models.masters.urls')),
    path('transactional/', include('models.transactional.urls')),
    
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT) 
