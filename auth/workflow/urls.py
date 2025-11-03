from django.urls import path
from . import views

app_name = 'workflows'

urlpatterns = [
    # Workflow endpoints
    path('workflows/', views.workflow_list, name='workflow-list'),
    path('workflows/create/', views.workflow_create, name='workflow-create'),
    path('workflows/<int:pk>/update/', views.workflow_update, name='workflow-update'),
    path('workflows/<int:pk>/delete/', views.workflow_delete, name='workflow-delete'),
    # WorkflowStage endpoints
    path('stages/', views.workflow_stage_list, name='workflow-stage-list'),
    path('stages/create/', views.workflow_stage_create, name='workflow-stage-create'),
    path('stages/<int:pk>/update/', views.workflow_stage_update, name='workflow-stage-update'),
    path('stages/<int:pk>/delete/', views.workflow_stage_delete, name='workflow-stage-delete'),
    # WorkflowTransition endpoints
    path('transitions/', views.workflow_transition_list, name='workflow-transition-list'),
    path('transitions/create/', views.workflow_transition_create, name='workflow-transition-create'),
    path('transitions/<int:pk>/update/', views.workflow_transition_update, name='workflow-transition-update'),
    path('transitions/<int:pk>/delete/', views.workflow_transition_delete, name='workflow-transition-delete'),
    # StagePermission endpoints
    path('permissions/', views.stage_permission_list, name='stage-permission-list'),
    path('permissions/create/', views.stage_permission_create, name='stage-permission-create'),
    path('permissions/<int:pk>/update/', views.stage_permission_update, name='stage-permission-update'),
    path('permissions/<int:pk>/delete/', views.stage_permission_delete, name='stage-permission-delete'),
]