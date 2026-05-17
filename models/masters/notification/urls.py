from django.urls import path
from . import views

urlpatterns = [
    # Notification APIs
    path('create/', views.NotificationCreateAPIView.as_view(), name='notification-create'),
    path('list/', views.NotificationListAPIView.as_view(), name='notification-list'),
    path('public/', views.NotificationPublicListAPIView.as_view(), name='notification-public-list'),
    path('download/<int:pk>/', views.NotificationDownloadAPIView.as_view(), name='notification-download'),
    path('detail/<int:pk>/', views.NotificationDetailAPIView.as_view(), name='notification-detail'),
    path('update/<int:pk>/', views.NotificationUpdateAPIView.as_view(), name='notification-update'),
    path('delete/<int:pk>/', views.NotificationDeleteAPIView.as_view(), name='notification-delete'),
]
