from django.apps import AppConfig


class BrandWarehouseConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'models.transactional.supply_chain.brand_warehouse'
    verbose_name = 'Brand Warehouse'

    def ready(self):
        """Import signals when the app is ready"""
        try:
            import models.transactional.supply_chain.brand_warehouse.signals
        except ImportError:
            pass