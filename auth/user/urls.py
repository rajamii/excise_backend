from django.urls import path, include
from .views import (
    register_user,
    licensee_signup,
    licensee_register_after_verification,
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
    verify_otp_for_registration,
    verify_otp_api,
    # LicenseeProfile views (moved from core)
    LicenseeProfileListView,
    LicenseeProfileDetailView,
    LicenseeProfileUpdateView,
    LicenseeProfileDeleteView,
    MyLicenseeProfileView,
)

# ── LicenseeProfile sub-patterns ─────────────────────────────────────────────
licenseeprofile_patterns = [
    path('',              LicenseeProfileListView.as_view(),   name='licenseeprofile-list'),
    path('me/',           MyLicenseeProfileView.as_view(),     name='licenseeprofile-me'),
    path('<int:pk>/',     LicenseeProfileDetailView.as_view(), name='licenseeprofile-detail'),
    path('<int:pk>/update/', LicenseeProfileUpdateView.as_view(), name='licenseeprofile-update'),
    path('<int:pk>/delete/', LicenseeProfileDeleteView.as_view(), name='licenseeprofile-delete'),
]

urlpatterns = [
    # Captcha
    path('get_captcha/', get_captcha, name='captcha'),
    path('', include('captcha.urls')),

    # Auth endpoints
    path('login/',         LoginAPI.as_view(),      name='user-login'),
    path('logout/',        LogoutAPI.as_view(),     name='user-logout'),
    path('token/refresh/', TokenRefreshAPI.as_view(), name='token-refresh'),

    # OTP endpoints
    path('otp/',        send_otp_api,                name='send-otp'),
    path('otp/verify/', verify_otp_for_registration, name='otp-verify'),
    path('otp/login/',  verify_otp_api,              name='otp-login'),

    # User management
    path('register/',          register_user,                        name='user-register'),
    path('register/licensee/', licensee_signup,                      name='licensee-signup'),
    path('register/licensee/final/', licensee_register_after_verification, name='licensee-register-otp-complete'),
    path('',           UserListView.as_view(),   name='user-list'),
    path('me/',        CurrentUserAPI.as_view(), name='current-user'),
    path('<int:pk>/detail/', UserDetailView.as_view(), name='user-detail'),
    path('<int:pk>/update/', UserUpdateView.as_view(), name='user-update'),
    path('<int:pk>/delete/', UserDeleteView.as_view(), name='user-delete'),

    # LicenseeProfile CRUD  ← moved from core
    path('licensee-profiles/', include(licenseeprofile_patterns)),
]