
from django.urls import path, include
from .views import (
    UserAPI,
    LoginAPI,
    LogoutAPI,
    TokenRefreshAPI,
    send_otp_API,
    verify_otp_API,
    get_captcha
)
from roles.views import role_list

# from django.contrib import admin

urlpatterns = [
    # captcha
    path('get_captcha/', get_captcha, name='captcha'), 
    path('',include('captcha.urls')), 

    # Token Refresh
    path('token/refresh/', TokenRefreshAPI.as_view(), name='token-refresh'),

    # path('user/', include('djano.contrib.auth.urls')),
    # User CRUD
    path('register/'               ,UserAPI.as_view() , name='user-register'),
    path('detail/<str:username>/'  ,UserAPI.as_view() , name='user-detail'  ),
    path('list/'                   ,UserAPI.as_view() , name='user-list'    ),
    path('update/<str:username>/'  ,UserAPI.as_view() , name='user-update'  ),
    path('delete/<str:username>/'  ,UserAPI.as_view() , name='user-delete'  ),

    #Auth
    path('login/'   ,LoginAPI.as_view()  , name='user-login'  ),
    path('logout/'  ,LogoutAPI.as_view() , name='user-logout' ),

    # OTP
    path('otp/' ,send_otp_API , name='send-otp'),
    path('otp/login/' , verify_otp_API , name='otp-login'),

    # Role List
    path('roles/', role_list, name='role-list'),  # Role list endpoint
]
