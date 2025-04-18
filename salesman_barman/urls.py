from django.conf import settings
from django.conf.urls.static import static
from django.urls import path
from .views import (
    SalesmanCreateView,
    SalesmanListView,
)

urlpatterns = [
    path('create/', SalesmanCreateView.as_view(), name='salesmanbarman-create'),
    path('list/', SalesmanListView.as_view(), name='salesmanbarman-list-all'),
    path('detail/<int:pk>/', SalesmanListView.as_view(), name='salesmanbarman-detail'),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
