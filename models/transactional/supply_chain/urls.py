from django.urls import include, path

urlpatterns = [
    path('bulk-spirit/', include('models.transactional.supply_chain.bulk_spirit.urls')),
    path('', include('models.transactional.supply_chain.ena_distillery_details.urls')),
    path('checkposts/', include('models.transactional.supply_chain.ena_checkpost.urls')),
    path('purposes/', include('models.transactional.supply_chain.ena_purpose.urls')),
    path('ena-requisitions/', include('models.transactional.supply_chain.ena_requisition_details.urls')),
    path('liquor-data/', include('models.transactional.supply_chain.liquor_data.urls')),
    path('distributor-data/', include('models.transactional.supply_chain.distributor_data_details.urls')),
    # Add other supply chain URLs here
]
