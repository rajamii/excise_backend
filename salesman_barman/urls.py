from django.urls import path

from .views import SalesmanBarmanView

urlpatterns = [

    path('salesman_barman/' , SalesmanBarmanView.as_view(), name = 'salesman_barman-create'),
    
]
