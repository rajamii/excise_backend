from django.conf import settings
from django.conf.urls.static import static
from django.urls import path, register_converter

from . import views


class EverythingConverter:
    """Matches any non-empty string including slashes — used for application IDs."""
    regex = '.+'

    def to_python(self, value):
        return value

    def to_url(self, value):
        return value


register_converter(EverythingConverter, 'everything')

app_name = 'company_collaboration'

urlpatterns = [
    # Application lifecycle
    path('apply/',            views.create_company_collaboration, name='apply'),
    path('list/',             views.list_company_collaborations,  name='list'),
    path('detail/<everything:application_id>/', views.company_collaboration_detail, name='detail'),

    # Workflow actions  ← NEW
    # POST body: { "action": "FORWARD|APPROVE|REJECT|RAISE_OBJECTION|RESPOND_OBJECTION|WITHDRAW", "remarks": "..." }
    path('workflow-action/<everything:application_id>/', views.workflow_action, name='workflow-action'),

    # Dashboard / reporting
    path('dashboard-counts/', views.dashboard_counts,  name='dashboard-counts'),
    path('list-by-status/',   views.application_group, name='applications-by-status'),
]

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)