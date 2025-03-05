# excise/urls.py
from django.urls import path
from .views import *

urlpatterns = [
    # User Registration/Signup
    path('register/', UserRegistrationView.as_view(), name='user-register'),

    # Login using Username & Password
    path('login/', UserLoginView.as_view(), name='user-login'),

    # Login using Phone Number & OTP
    path('send_otp/', SendOTP.as_view(), name='send-otp'),
    path('otp_login/', OTPLoginView.as_view(), name='otp-login'),
    
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
    path('subdivision/view/',SubdivisionView.as_view(),name='subdivision-view'),
    path('subdivision/by-district-code/<int:district_code>/', GetSubdivisionByDistrictCode.as_view(), name='subdivision-by-district-code'),

    path('dashboard/', DashboardCountView.as_view(), name='dashboard'),
]
