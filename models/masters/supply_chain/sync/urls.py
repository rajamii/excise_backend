from django.urls import path
from . import views

urlpatterns = [
    path('factory-list/', views.FactoryListView.as_view(), name='sync-factory-list'),
    path('liquor-type-list/', views.LiquorTypeListView.as_view(), name='sync-liquor-type-list'),
    path('brand-list/', views.BrandListView.as_view(), name='sync-brand-list'),
    path('bottle-type-list/', views.BottleTypeListView.as_view(), name='sync-bottle-type-list'),
    path('bottle-size-list/', views.BottleSizeListView.as_view(), name='sync-bottle-size-list'),
    path('update-sync-status/', views.UpdateSyncStatusView.as_view(), name='sync-update-status'),
]
