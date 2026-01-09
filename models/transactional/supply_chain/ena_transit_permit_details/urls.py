from django.urls import path
from .views import SubmitTransitPermitAPIView, GetTransitPermitAPIView

urlpatterns = [
    path('submit/', SubmitTransitPermitAPIView.as_view(), name='submit-transit-permit'),
    path('', GetTransitPermitAPIView.as_view(), name='get-transit-permits'),
]
