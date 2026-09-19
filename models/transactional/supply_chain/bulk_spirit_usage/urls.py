from django.urls import path
from .views import (
    EnaBulkSpiritUsageListCreateAPIView,
    EnaBulkSpiritUsageInventorySummaryAPIView,
    EnaBulkSpiritUsagePerformActionAPIView,
)

app_name = 'bulk_spirit_usage'

urlpatterns = [
    path('', EnaBulkSpiritUsageListCreateAPIView.as_view(), name='list-create'),
    path('inventory-summary/', EnaBulkSpiritUsageInventorySummaryAPIView.as_view(), name='inventory-summary'),
    path('<int:pk>/perform-action/', EnaBulkSpiritUsagePerformActionAPIView.as_view(), name='perform-action'),
]
