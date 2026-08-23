from django.urls import path
from . import views

urlpatterns = [
    path('bulk-spirit/factories/', views.secretary_bulk_spirit_factories, name='secretary_bulk_spirit_factories'),
    path('bulk-spirit/summary/', views.secretary_bulk_spirit_summary, name='secretary_bulk_spirit_summary'),
    path('licenses/', views.secretary_licenses_overview, name='secretary_licenses_overview'),
    path('imfl/', views.secretary_imfl_overview, name='secretary_imfl_overview'),
]
