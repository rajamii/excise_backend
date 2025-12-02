from django.urls import path
from .views import (
    EnaRequisitionDetailListCreateAPIView,
    EnaRequisitionDetailRetrieveUpdateDestroyAPIView,
    GetNextRefNumberAPIView,
    PerformRequisitionActionAPIView,
)


app_name = 'ena_requisition_details'


urlpatterns = [
    path('', EnaRequisitionDetailListCreateAPIView.as_view(), name='list-create'),
    path('<int:pk>/', EnaRequisitionDetailRetrieveUpdateDestroyAPIView.as_view(), name='detail'),
    path('next-ref-number/', GetNextRefNumberAPIView.as_view(), name='next-ref-number'),
    path('<int:pk>/perform-action/', PerformRequisitionActionAPIView.as_view(), name='perform-action'),
]


