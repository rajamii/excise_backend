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

    # Temporary Document Upload & Management endpoints:
    path('temporary-upload/', views.upload_temporary_document, name='temporary_upload'),
    path('temporary-documents/', views.list_temporary_documents, name='temporary_documents'),
    path('temporary-download/<str:application_type>/<str:document_field>/', views.download_temporary_document, name='temporary_download'),
    path('temporary-delete/<str:application_type>/<str:document_field>/', views.delete_temporary_document, name='temporary_delete'),
    path('temporary-delete/', views.delete_temporary_document, name='temporary_delete_body'),
]
