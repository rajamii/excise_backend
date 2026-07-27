from rest_framework import serializers

from auth.workflow.serializers import WorkflowObjectionSerializer, WorkflowTransactionSerializer

from .models import LabelRegistration, LabelRegistrationDocument


class LabelRegistrationDocumentSerializer(serializers.ModelSerializer):
    file_url = serializers.FileField(source='file', read_only=True)

    class Meta:
        model = LabelRegistrationDocument
        fields = [
            'id',
            'document_key',
            'document_name',
            'file',
            'file_url',
            'mime_type',
            'uploaded_at',
        ]
        read_only_fields = fields


class LabelRegistrationSerializer(serializers.ModelSerializer):
    current_stage_name = serializers.CharField(source='current_stage.name', read_only=True)
    transactions = WorkflowTransactionSerializer(many=True, read_only=True)
    objections = WorkflowObjectionSerializer(many=True, read_only=True)
    documents = LabelRegistrationDocumentSerializer(many=True, read_only=True)

    class Meta:
        model = LabelRegistration
        fields = '__all__'
        read_only_fields = [
            'application_id',
            'applicant',
            'workflow',
            'current_stage',
            'current_stage_name',
            'status',
            'is_approved',
            'created_at',
            'updated_at',
            'transactions',
            'objections',
            'documents',
        ]

