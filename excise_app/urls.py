# excise/urls.py
from django.urls import path , include
from .views import *



urlpatterns = [
    # User Registration/Signup
    path('',include('user.urls') ),

    path('get_captcha/', get_captcha, name='captcha'), 
    path('',include('captcha.urls')), 
    # Login using Phone Number & OTP
    path('send_otp/', SendOTP.as_view(), name='send-otp'),
    path('otp_login/', OTPLoginView.as_view(), name='otp-login'),

    #UserDetails endpoint
    # path('userdetails/',UserDetails.as_view(), name='user_details'),
    # path('users/', UserListView.as_view(), name='user-list'),

    #DashboardCount View
    path('dashboard/', DashboardCountView.as_view(), name='dashboard'),
]
