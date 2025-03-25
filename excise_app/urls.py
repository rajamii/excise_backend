# excise/urls.py
from django.urls import path , include
from .views import *



urlpatterns = [

    path('',include('user.urls') ), 

    path('get_captcha/', get_captcha, name='captcha'), 

    path('',include('captcha.urls')), 



    path('dashboard/', DashboardCountView.as_view(), name='dashboard'),
]
