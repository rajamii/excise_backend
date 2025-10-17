from django.urls import path
from .views import (
    EnaRequisitionDetailListCreateAPIView,
    EnaRequisitionDetailRetrieveUpdateDestroyAPIView,
)


app_name = 'ena_requisition_details'


urlpatterns = [
    path('', EnaRequisitionDetailListCreateAPIView.as_view(), name='list-create'),
    path('<int:pk>/', EnaRequisitionDetailRetrieveUpdateDestroyAPIView.as_view(), name='detail'),
]


