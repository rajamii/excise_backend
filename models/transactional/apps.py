from django.apps import AppConfig


class AppNameConfig(AppConfig):
    name = 'models.transactional'
    verbose_name = 'transactional'

    def ready(self):
        from .dashboard_cache_signals import register_dashboard_cache_invalidation

        register_dashboard_cache_invalidation()
