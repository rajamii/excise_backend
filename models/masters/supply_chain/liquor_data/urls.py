from django.urls import path
from . import views

urlpatterns = [
    path('brands/', views.BrandSizeListView.as_view(), name='brand-size-list'),
    path('rates/', views.LiquorRatesView.as_view(), name='liquor-rates'),
    path('approved-brands/', views.ApprovedBrandDetailsView.as_view(), name='approved-brands'),
]