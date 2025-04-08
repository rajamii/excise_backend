from django.conf import settings
from django.conf.urls.static import static
from django.urls import path
from .views import (
    SalesmanCreateView,
    SalesmanListView,
)

urlpatterns = [
    path('salesmanbarman/create/', SalesmanCreateView.as_view(), name='salesmanbarman-create'),
    path('salesmanbarman/list/', SalesmanListView.as_view(), name='salesmanbarman-list-all'),
    path('salesmanbarman/detail/<int:pk>/', SalesmanListView.as_view(), name='salesmanbarman-detail'),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
