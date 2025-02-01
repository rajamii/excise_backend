# excise/urls.py
from django.urls import path
from .views import *

urlpatterns = [
    path('register/', UserRegistrationView.as_view(), name='user-register'),
     path('login/', UserLoginView.as_view(), name='user-login'),
     #getcaptcha endpoint
    path('get_captcha/', get_captcha, name='captcha'), 

      #UserDetails endpoint
    path('userdetails/',UserDetails.as_view(), name='user_details'),


    path('district/', DistrictAdd.as_view(), name='district'),
    path('district/<int:id>/', DistrictAdd.as_view(), name='district-isActive'),
    path('district/view/', DistrictView.as_view(), name='district-view'),


        # Subdivision Add, put and view
    path('subdivision/', SubDivisonApi.as_view(), name='subdivision'),
    path('subdivision/<int:id>/', SubDivisonApi.as_view(), name='subdivision-isActive'),

    path('dashboard/', DashboardCountView.as_view(), name='dashboard'),
]
