
from django.urls import path
from .views import (
    UserAPI,
    LoginAPI,
    LogoutAPI,
    send_otp_API,
    verify_otp_API,
)


# from django.contrib import admin

urlpatterns = [

    # path('user/', include('djano.contrib.auth.urls')),
    path('user/register/'               ,UserAPI.as_view() , name='user-register'),
    path('user/detail/<str:username>/'  ,UserAPI.as_view() , name='user-detail'  ),
    path('user/list/'                   ,UserAPI.as_view() , name='user-list'    ),
    path('user/update/<str:username>/'  ,UserAPI.as_view() , name='user-update'  ),
    path('user/delete/<str:username>/'  ,UserAPI.as_view() , name='user-delete'  ),


    path('user/login/'   ,LoginAPI.as_view()  , name='user-login'  ),
    path('user/logout/'  ,LogoutAPI.as_view() , name='user-logout' ),

    path('user/otp/get/' ,send_otp_API , name='send-otp'),
    path('user/otp/login/' , verify_otp_API , name='otp-login'),

]
