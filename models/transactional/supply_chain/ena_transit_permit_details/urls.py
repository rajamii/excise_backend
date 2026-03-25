from django.urls import path
from .views import (
    SubmitTransitPermitAPIView,
    GetTransitPermitAPIView,
    PerformTransitPermitActionAPIView,
    GetTransitPermitDetailAPIView,
    PublicTransitPermitAPIView,
)

urlpatterns = [
    path('submit/', SubmitTransitPermitAPIView.as_view(), name='submit-transit-permit'),
    path('public/', PublicTransitPermitAPIView.as_view(), name='public-transit-permits'),
    path('public/<path:bill_no>/', PublicTransitPermitAPIView.as_view(), name='public-transit-permits-by-bill'),
    path('', GetTransitPermitAPIView.as_view(), name='get-transit-permits'),
    path('<int:pk>/', GetTransitPermitDetailAPIView.as_view(), name='get-transit-permit-detail'),
    path('action/<int:pk>/', PerformTransitPermitActionAPIView.as_view(), name='transit-permit-action'),
]
