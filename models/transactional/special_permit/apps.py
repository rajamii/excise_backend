from django.apps import AppConfig


class SpecialPermitConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'models.transactional.special_permit'
    label = 'special_permit'
    verbose_name = 'special_permit'
