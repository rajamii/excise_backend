from django.urls import path, register_converter

from . import views


class EverythingConverter:
    regex = '.+'

    def to_python(self, value):
        return value

    def to_url(self, value):
        return value


register_converter(EverythingConverter, 'everything')

urlpatterns = [
    # /transactional/validate/license/<code>/pdf/
    path('license/<everything:code>/pdf/', views.validate_license_pdf, name='validate-license-pdf'),
    # /transactional/validate/license/pdf/?code=<code>
    path('license/pdf/', views.validate_license_pdf_qs, name='validate-license-pdf-qs'),
]
