from django.urls import include, path

urlpatterns = [
    path('bulk-spirit/', include('models.masters.supply_chain.bulk_spirit.urls')),
    path('checkposts/', include('models.masters.supply_chain.ena_checkpost.urls')),
    path('purposes/', include('models.masters.supply_chain.ena_purpose.urls')),
    path('liquor-data/', include('models.masters.supply_chain.liquor_data.urls')),
    path('distributor-data/', include('models.masters.supply_chain.distributor_data_details.urls')),
]
