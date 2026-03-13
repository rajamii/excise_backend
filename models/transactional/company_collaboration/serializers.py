from rest_framework import serializers

from auth.workflow.serializers import WorkflowObjectionSerializer, WorkflowTransactionSerializer

from .models import CompanyCollaboration


class CompanyCollaborationSerializer(serializers.ModelSerializer):
    application_id = serializers.CharField(read_only=True)
    current_stage = serializers.PrimaryKeyRelatedField(read_only=True)
    workflow = serializers.PrimaryKeyRelatedField(read_only=True)
    current_stage_name = serializers.CharField(source='current_stage.name', read_only=True)
    is_approved = serializers.BooleanField(read_only=True)
    transactions = WorkflowTransactionSerializer(many=True, read_only=True)
    objections = WorkflowObjectionSerializer(many=True, read_only=True)

    class Meta:
        model = CompanyCollaboration
        fields = '__all__'
        read_only_fields = [
            'application_id',
            'workflow',
            'current_stage',
            'current_stage_name',
            'is_approved',
            'applicant',
            'created_at',
            'updated_at',
        ]

