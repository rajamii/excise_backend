from django.urls import path
from . import views

urlpatterns = [
    path('liquor-types/', views.MasterLiquorTypeListView.as_view(), name='master-liquor-type-list'),
    path('brands/', views.BrandSizeListView.as_view(), name='brand-size-list'),
    path('rates/', views.LiquorRatesView.as_view(), name='liquor-rates'),
]
