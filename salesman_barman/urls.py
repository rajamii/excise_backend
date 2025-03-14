from django.urls import path

from .views import SalesmanBarmanView

urlpatterns = [


    # POST for creation of a salesman_barman

    path('salesman_barman/' , SalesmanBarmanView.as_view(), name = 'salesman_barman-create'),

    # GET for Listing a specific police station 
    
    path('salesman_barman/<int:sb>' , SalesmanBarmanView.as_view() , name = 'salesman_barman-detail'),

    # PUT for updation of a salesman_barman

    path('salesman_barmans/<int:id>' , SalesmanBarmanView.as_view() , name = 'salesman_barman-update'),

    # GET for listing all police stations
    
    path('salesman_barmans/' , SalesmanBarmanView.as_view() , name = 'salesman_barman-list')
    
]
