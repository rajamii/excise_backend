from django.urls import include, path

urlpatterns = [
    path('bulk-spirit/', include('models.transactional.supply_chain.bulk_spirit.urls')),
    # Add other supply chain URLs here
]
