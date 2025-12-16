from django.urls import path, register_converter
from django.conf import settings
from django.conf.urls.static import static
from . import views

class EverythingConverter:
    regex = '.+'

    def to_python(self, value):
        return value

    def to_url(self, value):
        return value
    
register_converter(EverythingConverter, 'everything')

app_name = 'salesman_barman'

urlpatterns = [
    path('apply/', views.create_salesman_barman, name='apply'),
    path('list/', views.list_salesman_barman, name='list'),
    path('detail/<everything:application_id>/', views.salesman_barman_detail, name='detail'),
    # path('<everything:application_id>/advance/<int:stage_id>/', views.advance_application, name='advance'),
    # path('<everything:application_id>/next-stages/', views.get_next_stages, name='next-stages'),
    path('dashboard-counts/', views.dashboard_counts, name='sb-dashboard-counts'),
    path('list-by-status/', views.application_group, name='applications-by-status'),
]

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)