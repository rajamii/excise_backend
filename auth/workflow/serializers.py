from rest_framework import serializers
from .models import Workflow, WorkflowStage, WorkflowTransition, StagePermission, Transaction, Objection, Rejection
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
    raisedByName = serializers.SerializerMethodField()
    resolvedByName = serializers.SerializerMethodField()
    raisedAt = serializers.DateTimeField(source='raised_on', read_only=True)
    resolvedAt = serializers.DateTimeField(source='resolved_on', read_only=True)
    fieldName = serializers.CharField(source='field_name', read_only=True)
    isResolved = serializers.BooleanField(source='is_resolved', read_only=True)
    beforeContent = serializers.CharField(source='before_content', read_only=True, allow_null=True)
    afterContent = serializers.CharField(source='after_content', read_only=True, allow_null=True)

    def get_raisedByName(self, obj):
        user = getattr(obj, 'raised_by', None)
        if not user:
            return None
        name = f"{getattr(user, 'first_name', '')} {getattr(user, 'last_name', '')}".strip()
        return name or getattr(user, 'username', None)

    def get_resolvedByName(self, obj):
        user = getattr(obj, 'resolved_by', None)
        if not user:
            return None
        name = f"{getattr(user, 'first_name', '')} {getattr(user, 'last_name', '')}".strip()
        return name or getattr(user, 'username', None)

    class Meta:
        model = Objection
        fields = [
            'id',
            'content_type',
            'object_id',
            'fieldName',
            'remarks',
            'beforeContent',
            'afterContent',
            'raised_by',
            'raisedByName',
            'raisedAt',
            'stage',
            'isResolved',
            'resolvedAt',
            'resolved_by',
            'resolvedByName',
        ]

class WorkflowRejectionSerializer(serializers.ModelSerializer):
    rejected_by = UserSerializer(read_only=True)
    stage = WorkflowStageSerializer(read_only=True)

    class Meta:
        model = Rejection
        fields = ['id', 'content_type', 'object_id', 'remarks', 'rejected_by', 'stage', 'rejected_on']
