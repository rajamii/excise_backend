from django.urls import path
from .views import ManufacturingUnitListView, UserUnitsAPIView, UserProfileAPIView

urlpatterns = [
    path('units/', ManufacturingUnitListView.as_view(), name='manufacturing-units'),
    path('user-units/', UserUnitsAPIView.as_view(), name='user-registered-units'),
    path('profile/', UserProfileAPIView.as_view(), name='user-profile'),
]
