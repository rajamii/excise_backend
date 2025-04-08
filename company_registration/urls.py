from django.conf import settings
from django.conf.urls.static import static
from django.urls import path
from .views import (
    CompanyCreateView,
    CompanyListView,
)

urlpatterns = [
    path('company/create/', CompanyCreateView.as_view(), name='company-create'),
    path('company/list/', CompanyListView.as_view(), name='company-list-all'),
    path('company/detail/<int:pk>/', CompanyListView.as_view(), name='company-details'),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
