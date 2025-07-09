from django.contrib import admin
from django.urls import path, include

urlpatterns = [

    path('admin/', admin.site.urls),
    path('users/', include('auth.user.urls')),
    path('roles/', include('auth.role.urls')),
        
]
