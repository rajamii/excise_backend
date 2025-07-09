from django.urls import path
from .views import (
    register_user,
    UserListView,
    UserDetailView,
    UserUpdateView,
    UserDeleteView
)

urlpatterns = [
    path('register/', register_user, name='user-register'),
    path('', UserListView.as_view(), name='user-list'),
    path('<int:pk>/', UserDetailView.as_view(), name='user-detail'),
    path('<int:pk>/update/', UserUpdateView.as_view(), name='user-update'),
    path('<int:pk>/delete/', UserDeleteView.as_view(), name='user-delete'),
]
