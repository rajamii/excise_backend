from django.urls import path
from .views import (
    SalesmanCreateView,
    SalesmanListView,
)

urlpatterns = [
    path('salesmanbarman/create/', SalesmanCreateView.as_view() , name = 'salesmanbarman-create'),
    path('salesmanbarman/list/<int:pk>' , SalesmanListView.as_view() , name = 'salesmanbarman-list'),

]
