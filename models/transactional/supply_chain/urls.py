from django.urls import include, path

urlpatterns = [
    path('ena-requisitions/', include('models.transactional.supply_chain.ena_requisition_details.urls')),
    path('ena-revalidations/', include('models.transactional.supply_chain.ena_revalidation_details.urls')),
    path('ena-cancellation-details/', include('models.transactional.supply_chain.ena_cancellation_details.urls')),
    path('hologram/', include('models.transactional.supply_chain.hologram.urls')),
    path('transit-permits/', include('models.transactional.supply_chain.ena_transit_permit_details.urls')),
    path('brand-warehouse/', include('models.transactional.supply_chain.brand_warehouse.urls')),
    # Add other supply chain URLs here
]

