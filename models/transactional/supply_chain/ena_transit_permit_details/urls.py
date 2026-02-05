from django.urls import path
from .views import SubmitTransitPermitAPIView, GetTransitPermitAPIView, PerformTransitPermitActionAPIView, GetTransitPermitDetailAPIView

urlpatterns = [
    path('submit/', SubmitTransitPermitAPIView.as_view(), name='submit-transit-permit'),
    path('', GetTransitPermitAPIView.as_view(), name='get-transit-permits'),
    path('<int:pk>/', GetTransitPermitDetailAPIView.as_view(), name='get-transit-permit-detail'),
    path('action/<int:pk>/', PerformTransitPermitActionAPIView.as_view(), name='transit-permit-action'),
]
