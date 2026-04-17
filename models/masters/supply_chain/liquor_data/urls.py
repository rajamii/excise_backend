from django.urls import path
from . import views

urlpatterns = [
    path('liquor-types/', views.MasterLiquorTypeListView.as_view(), name='master-liquor-type-list'),
    path('liquor-categories/', views.MasterLiquorCategoryListView.as_view(), name='master-liquor-category-list'),
    path('master-brands/', views.master_brand_list, name='master-brand-list'),
    path('master-brands/create/', views.master_brand_create, name='master-brand-create'),
    path('master-factories/', views.master_factory_list, name='master-factory-list'),
    path('master-factories/create/', views.master_factory_create, name='master-factory-create'),
    path('bottle-types/', views.master_bottle_type_list, name='master-bottle-type-list'),
    path('bottle-types/create/', views.master_bottle_type_create, name='master-bottle-type-create'),
    path('bottle-types/<int:pk>/', views.MasterBottleTypeDetailView.as_view(), name='master-bottle-type-detail'),
    path('brands/', views.BrandSizeListView.as_view(), name='brand-size-list'),
    path('rates/', views.LiquorRatesView.as_view(), name='liquor-rates'),
]
