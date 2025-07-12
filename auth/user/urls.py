from django.urls import path, include
from .views import (
    register_user,
    UserListView,
    UserDetailView,
    CurrentUserAPI,
    UserUpdateView,
    UserDeleteView,
    TokenRefreshAPI,
    get_captcha,
    LoginAPI,
    LogoutAPI,
    send_otp_api,
    verify_otp_api
)

urlpatterns = [
    # Captcha
    path('get_captcha/', get_captcha, name='captcha'),
    path('', include('captcha.urls')),

    # Auth endpoints
    path('login/', LoginAPI.as_view(), name='user-login'),  
    path('logout/', LogoutAPI.as_view(), name='user-logout'), 
    path('token/refresh/', TokenRefreshAPI.as_view(), name='token-refresh'),

    # OTP endpoints
    path('otp/', send_otp_api, name='send-otp'), 
    path('otp/login/', verify_otp_api, name='otp-login'), 

    # User management
    path('register/', register_user, name='user-register'),
    path('', UserListView.as_view(), name='user-list'),
    path('<int:pk>/detail/', UserDetailView.as_view(), name='user-detail'),
    path('me/', CurrentUserAPI.as_view(), name='current-user'),
    path('<int:pk>/update/', UserUpdateView.as_view(), name='user-update'),
    path('<int:pk>/delete/', UserDeleteView.as_view(), name='user-delete'),
]
