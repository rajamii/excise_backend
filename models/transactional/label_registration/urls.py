from django.conf import settings
from django.conf.urls.static import static
from django.urls import path, register_converter

from . import views


class EverythingConverter:
    regex = '.+'

    def to_python(self, value):
        return value

    def to_url(self, value):
        return value


register_converter(EverythingConverter, 'everything')

app_name = 'label_registration'

urlpatterns = [
    path('apply/', views.apply_label_registration, name='apply'),
    path('list/', views.list_label_registrations, name='list'),
    path('detail/<everything:application_id>/', views.label_registration_detail, name='detail'),
]

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

