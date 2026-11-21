from django.urls import path, register_converter
from . import views


class EverythingConverter:
    regex = '.+'

    def to_python(self, value):
        return value

    def to_url(self, value):
        return value

try:
    register_converter(EverythingConverter, 'everything_dms')
except Exception:
    pass

app_name = 'dms_documents'

urlpatterns = [
    # Universal download URL: /transactional/dms/document/<application_id>/<document_field>/
    path('document/<everything_dms:application_id>/<str:document_field>/', views.download_universal_dms_document, name='download_universal_dms_document'),
    path('<everything_dms:application_id>/document/<str:document_field>/', views.download_universal_dms_document, name='download_universal_dms_document_alt'),
]
