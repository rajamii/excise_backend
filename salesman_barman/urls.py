from django.urls import path

form .views import SalesmanBarmanView

urlpatterns = [

    path('salesman_barman/' , SalesmanBarmanView.as_view(), name = 'salesman_barman-create'),
    
]
