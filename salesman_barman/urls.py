from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    SalesmanBarmanList,
    SalesmanBarmanDetails,
    DocumentsDetailsList,
    DocumentsDetailsDetails,
)

urlpatterns = [
    path('salesmanbarman/list/' , SalesmanBarmanList.as_view() , name='salesmanbarman-list'),
    path('salesmanbarman/create/' , SalesmanBarmanList.as_view() , name='salesmanbarman-create'),
    
    path('salesmanbarman/detail/<int:pk>' , SalesmanBarmanDetails.as_view() , name='salesmanbarman-detail'),
    path('salesmanbarman/update/<int:pk>' , SalesmanBarmanDetails.as_view() , name='salesmanbarman-update'),
    path('salesmanbarman/delete/<int:pk>' , SalesmanBarmanDetails.as_view() , name='salesmanbarman-delete'),
       
]
