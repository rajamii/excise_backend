from django.contrib import admin
from django.urls import path, include

urlpatterns = [

    path('users/', include('auth.user.urls')),
    path('roles/', include('auth.roles.urls')),
        
]
