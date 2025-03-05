from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('excise_app.urls')),
    path('captcha/',include('captcha.urls')),
    path('masters/', include('masters.urls')),
]
