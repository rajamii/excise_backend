from django.urls import path
from . import views

app_name = 'bulk_spirit'

urlpatterns = [
    path('bulk-spirit-types/', views.BulkSpiritTypeListAPIView.as_view(), name='bulk-spirit-types-list'),
]
