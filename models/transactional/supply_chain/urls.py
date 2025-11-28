from django.urls import include, path

urlpatterns = [
    path('ena-requisitions/', include('models.transactional.supply_chain.ena_requisition_details.urls')),
    # Add other supply chain URLs here
]
