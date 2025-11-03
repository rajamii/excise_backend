from rest_framework import serializers
from .models import Workflow, WorkflowStage, WorkflowTransition, StagePermission
from auth.roles.models import Role

class WorkflowSerializer(serializers.ModelSerializer):
    class Meta:
        model = Workflow
        fields = ['id', 'name', 'description']

class WorkflowStageSerializer(serializers.ModelSerializer):
    workflow = serializers.PrimaryKeyRelatedField(queryset=Workflow.objects.all())
    class Meta:
        model = WorkflowStage
        fields = ['id', 'workflow', 'name', 'description', 'is_initial', 'is_final']

class WorkflowTransitionSerializer(serializers.ModelSerializer):
    workflow = serializers.PrimaryKeyRelatedField(queryset=Workflow.objects.all())
    from_stage = serializers.PrimaryKeyRelatedField(queryset=WorkflowStage.objects.all())
    to_stage = serializers.PrimaryKeyRelatedField(queryset=WorkflowStage.objects.all())
    class Meta:
        model = WorkflowTransition
        fields = ['id', 'workflow', 'from_stage', 'to_stage', 'condition']

class StagePermissionSerializer(serializers.ModelSerializer):
    stage = serializers.PrimaryKeyRelatedField(queryset=WorkflowStage.objects.all())
    role = serializers.PrimaryKeyRelatedField(queryset=Role.objects.all())
    class Meta:
        model = StagePermission
        fields = ['id', 'stage', 'role', 'can_process']