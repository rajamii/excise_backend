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
    dms_documents = serializers.SerializerMethodField()

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
            'dms_documents',
        ]

    def get_dms_documents(self, obj):
        try:
            from models.transactional.dms_documents.models import DMSDocumentLabel
            docs = list(DMSDocumentLabel.objects.filter(application_id=obj.application_id))
            return [
                {
                    "document_field": doc.document_field,
                    "dms_reference": doc.dms_reference,
                    "original_filename": doc.original_filename,
                    "file_size": doc.file_size,
                    "mime_type": doc.mime_type,
                    "storage_type": doc.storage_type,
                    "dms_registration_no": doc.dms_registration_no,
                    "transaction_signature": doc.transaction_signature,
                    "uploaded_at": doc.created_at.isoformat() if doc.created_at else None,
                    "download_url": f"/transactional/label-registration/{obj.application_id}/document/{doc.document_field}/"
                }
                for doc in docs
            ]
        except Exception:
            return []

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        try:
            from models.transactional.dms_documents.models import DMSDocumentLabel
            docs = list(DMSDocumentLabel.objects.filter(application_id=instance.application_id))
            for d in docs:
                url = f"/transactional/label-registration/{instance.application_id}/document/{d.document_field}/"
                rep[d.document_field] = url
        except Exception:
            pass
        return rep

