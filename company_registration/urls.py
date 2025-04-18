from django.conf import settings
from django.conf.urls.static import static
from django.urls import path
from .views import (
    CompanyCreateView,
    CompanyListView,
)

urlpatterns = [
    # Endpoint to create a new company entry (POST)
    path('create/', CompanyCreateView.as_view(), name='company-create'),

    # Endpoint to list all company entries (GET)
    path('list/', CompanyListView.as_view(), name='company-list-all'),

    # Endpoint to get details of a specific company by primary key (GET)
    path('detail/<int:pk>/', CompanyListView.as_view(), name='company-details'),
]

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
