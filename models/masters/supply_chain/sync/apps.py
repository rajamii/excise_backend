from django.apps import AppConfig


class SyncConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'models.masters.supply_chain.sync'
    label = 'lmsdb_sync'
