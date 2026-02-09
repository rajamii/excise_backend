from rest_framework import serializers
from .models import Workflow, WorkflowStage, WorkflowTransition, StagePermission, Transaction, Objection
from auth.roles.models import Role
from auth.user.serializer import UserSerializer
from auth.roles.serializers import RoleSerializer

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

# shared in workflow/serializers.py
class WorkflowTransactionSerializer(serializers.ModelSerializer):
    performed_by = UserSerializer(read_only=True)
    forwarded_by = RoleSerializer(read_only=True)
    forwarded_to = RoleSerializer(read_only=True)
    class Meta:
        model = Transaction
        fields = '__all__'

class WorkflowObjectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Objection
        fields = '__all__'
