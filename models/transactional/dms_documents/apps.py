from django.apps import AppConfig


class DMSDocumentsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'models.transactional.dms_documents'
    label = 'dms_documents'
    verbose_name = 'DMS Uploaded Documents'
