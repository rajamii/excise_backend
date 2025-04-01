from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('excise_app.urls')),
    path('captcha/',include('captcha.urls')),
    path('masters/', include('masters.urls')),
    path('registration_renewal/', include('registration_renewal.urls')),
    path('salesman_barman/', include('salesman_barman.urls')),
    path('contact_us/', include('contact_us.urls')),


]
