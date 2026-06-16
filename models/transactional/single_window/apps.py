from django.apps import AppConfig


class SingleWindowConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "models.transactional.single_window"
