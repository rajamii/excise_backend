from django.apps import AppConfig


class AppNameConfig(AppConfig):
    name = 'models.transactional.logs'
    verbose_name = 'logs'

    def ready(self):
        import models.transactional.logs.signals
