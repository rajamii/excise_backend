from django.urls import include, path

urlpatterns = [
    path('ena-requisitions/', include('models.transactional.supply_chain.ena_requisition_details.urls')),
    path('ena-revalidations/', include('models.transactional.supply_chain.ena_revalidation_details.urls')),
    path('ena-cancellation-details/', include('models.transactional.supply_chain.ena_cancellation_details.urls')),
    # Add other supply chain URLs here
]
