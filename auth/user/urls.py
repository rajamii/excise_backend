from django.urls import path, include
from .views import (
    register_user,
    UserListView,
    UserDetailView,
    UserUpdateView,
    UserDeleteView,
    TokenRefreshAPI,
    get_captcha,
    login,
    logout,
    send_otp,
    verify_otp
)

urlpatterns = [
    # Captcha
    path('get_captcha/', get_captcha, name='captcha'),
    path('', include('captcha.urls')),

    # Auth endpoints
    path('login/', login, name='user-login'),           # function-based
    path('logout/', logout, name='user-logout'),        # function-based
    path('token/refresh/', TokenRefreshAPI.as_view(), name='token-refresh'),

    # OTP endpoints
    path('otp/', send_otp, name='send-otp'),        # function-based
    path('otp/login/', verify_otp, name='otp-login'),   # function-based

    # User management
    path('register/', register_user, name='user-register'),
    path('', UserListView.as_view(), name='user-list'),
    path('<int:pk>/', UserDetailView.as_view(), name='user-detail'),
    path('<int:pk>/update/', UserUpdateView.as_view(), name='user-update'),
    path('<int:pk>/delete/', UserDeleteView.as_view(), name='user-delete'),
]
