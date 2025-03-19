# excise/urls.py
from django.urls import path
from .views import *

urlpatterns = [
    # User Registration/Signup
    path('register/', UserRegistrationView.as_view(), name='user-register'),

    #getcaptcha endpoint
    # sends the captcha to user 

    path('get_captcha/', get_captcha, name='captcha'), 

    # Login using Username & Password
    # authenticates the user and checks for the captcha

    path('login/', UserLoginView.as_view(), name='user-login'),
    
    # Login using Phone Number & OTP
    path('send_otp/', SendOTP.as_view(), name='send-otp'),
    path('otp_login/', OTPLoginView.as_view(), name='otp-login'),

    #UserDetails endpoint
    path('userdetails/',UserDetails.as_view(), name='user_details'),
    path('users/', UserListView.as_view(), name='user-list'),

    #DashboardCount View
    path('dashboard/', DashboardCountView.as_view(), name='dashboard'),
]
