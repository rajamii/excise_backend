from django.urls import path
from .views import (
    EnaRequisitionDetailListCreateAPIView,
    EnaRequisitionDetailRetrieveUpdateDestroyAPIView,
    GetNextRefNumberAPIView,
    PerformRequisitionActionAPIView,
    RequisitionArrivalBulkLiterDetailAPIView,
    RequisitionArrivalBulkLiterDetailsListAPIView,
)


app_name = 'ena_requisition_details'


urlpatterns = [
    path('', EnaRequisitionDetailListCreateAPIView.as_view(), name='list-create'),
    path('<int:pk>/', EnaRequisitionDetailRetrieveUpdateDestroyAPIView.as_view(), name='detail'),
    path('next-ref-number/', GetNextRefNumberAPIView.as_view(), name='next-ref-number'),
    path('arrival-bulk-liter-details/', RequisitionArrivalBulkLiterDetailsListAPIView.as_view(), name='arrival-bulk-liter-details-list'),
    path('<int:pk>/perform-action/', PerformRequisitionActionAPIView.as_view(), name='perform-action'),
    path('<int:pk>/arrival-bulk-liter-details/', RequisitionArrivalBulkLiterDetailAPIView.as_view(), name='arrival-bulk-liter-details'),
]


