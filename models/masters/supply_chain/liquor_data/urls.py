from django.urls import path
from . import views

urlpatterns = [
    path('liquor-types/', views.MasterLiquorTypeListView.as_view(), name='master-liquor-type-list'),
    path('liquor-categories/', views.MasterLiquorCategoryListView.as_view(), name='master-liquor-category-list'),
    path('bottle-types/', views.MasterBottleTypeListCreateView.as_view(), name='master-bottle-type-list-create'),
    path('bottle-types/<int:pk>/', views.MasterBottleTypeDetailView.as_view(), name='master-bottle-type-detail'),
    path('brands/', views.BrandSizeListView.as_view(), name='brand-size-list'),
    path('rates/', views.LiquorRatesView.as_view(), name='liquor-rates'),
]
