from django.urls import path
from .views import ManufacturingUnitListView, SupplyChainUserProfileView, UserUnitsAPIView, SwitchUnitAPIView

urlpatterns = [
    path('units/', ManufacturingUnitListView.as_view(), name='manufacturing-units'),
    path('profile/', SupplyChainUserProfileView.as_view(), name='supply-chain-profile'),
    path('user-units/', UserUnitsAPIView.as_view(), name='user-registered-units'),
    path('switch-unit/', SwitchUnitAPIView.as_view(), name='switch-unit'),
]
