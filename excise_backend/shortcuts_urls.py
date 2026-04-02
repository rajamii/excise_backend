from django.urls import include, path, register_converter

from models.masters.supply_chain.liquor_data import views as liquor_data_views
from models.transactional.public_validation import views as public_validation_views


class EverythingConverter:
    regex = '.+'

    def to_python(self, value):
        return value

    def to_url(self, value):
        return value


register_converter(EverythingConverter, 'everything')


urlpatterns = [
    # Liquor-data master tables (short aliases)
    path('bottle-types/', liquor_data_views.MasterBottleTypeListCreateView.as_view(), name='short-bottle-types'),
    path('bottle-types/<int:pk>/', liquor_data_views.MasterBottleTypeDetailView.as_view(), name='short-bottle-types-detail'),
    path('liquor-types/', liquor_data_views.MasterLiquorTypeListView.as_view(), name='short-liquor-types'),
    path('liquor-categories/', liquor_data_views.MasterLiquorCategoryListView.as_view(), name='short-liquor-categories'),
    path('master-brands/', liquor_data_views.MasterBrandListListCreateView.as_view(), name='short-master-brands'),
    path('master-factories/', liquor_data_views.MasterFactoryListListCreateView.as_view(), name='short-master-factories'),
    path('brands/', liquor_data_views.BrandSizeListView.as_view(), name='short-brand-sizes'),
    path('rates/', liquor_data_views.LiquorRatesView.as_view(), name='short-liquor-rates'),

    # Transactional (short aliases)
    path(
        'brand-warehouse/',
        include('models.transactional.supply_chain.brand_warehouse.short_urls_brand_warehouse'),
    ),
    path(
        'brand-warehouse-utilization/',
        include('models.transactional.supply_chain.brand_warehouse.short_urls_utilization'),
    ),

    # Public validation (short alias)
    # /v/<validation-code>/  -> QR-friendly verification page (download only if valid)
    path('v/<everything:code>/', public_validation_views.validate_license_landing, name='validate-license-short'),
]

