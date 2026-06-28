from django.urls import path
from . import views

urlpatterns = [
    path('create/', views.PreventiveRaidCreateAPIView.as_view(), name='preventiveraid-create'),
    path('list/', views.PreventiveRaidListAPIView.as_view(), name='preventiveraid-list'),
    path('detail/<int:pk>/', views.PreventiveRaidDetailAPIView.as_view(), name='preventiveraid-detail'),
    path('update/<int:pk>/', views.PreventiveRaidUpdateAPIView.as_view(), name='preventiveraid-update'),
    path('delete/<int:pk>/', views.PreventiveRaidDeleteAPIView.as_view(), name='preventiveraid-delete'),
]
