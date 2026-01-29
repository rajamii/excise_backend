from django.urls import include, path

urlpatterns = [
    path('ena-distillery-types/', include('models.masters.supply_chain.ena_distillery_details.urls')),
    path('bulk-spirit/', include('models.masters.supply_chain.bulk_spirit.urls')),
    path('checkposts/', include('models.masters.supply_chain.ena_checkpost.urls')),
    path('purposes/', include('models.masters.supply_chain.ena_purpose.urls')),
    path('liquor-data/', include('models.masters.supply_chain.liquor_data.urls')),
    path('distributor-data/', include('models.masters.supply_chain.distributor_data_details.urls')),
    path('user-profile/', include('models.masters.supply_chain.profile.urls')),
    path('transit-permit/', include('models.masters.supply_chain.transit_permit.urls')),
    # path('vehicles/', include('models.masters.supply_chain.vehicles.urls')),
    # path('status-master/', include('models.masters.supply_chain.status_master.urls')),
]
