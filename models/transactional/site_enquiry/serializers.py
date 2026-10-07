from rest_framework import serializers
from models.transactional.site_enquiry.models import SiteEnquiryReport
from utils.file_validation import validate_uploaded_file


class SiteEnquiryReportSerializer(serializers.ModelSerializer):
    application_id = serializers.CharField(source='content_object.application_id', read_only=True)
    application_type = serializers.CharField(source='content_type.model', read_only=True)
    # Backward-compatible aliases used by some frontend screens.
    site_enquiry_is_reverted = serializers.BooleanField(source='is_reverted', read_only=True)
    revertedRemarks = serializers.CharField(source='reverted_remarks', read_only=True)
    revert_history = serializers.SerializerMethodField()

    class Meta:
        model = SiteEnquiryReport
        fields = '__all__'
        read_only_fields = [
            'created_at',
            'updated_at',
            'application_id',
            'application_type',
            'license_id',
            'content_type',
            'object_id',
            'is_reverted',
            'reverted_remarks',
            'reverted_at',
            'revert_history',
        ]

    def get_revert_history(self, obj):
        try:
            from auth.workflow.models import Revert
            reverts = Revert.objects.filter(
                content_type=obj.content_type,
                object_id=obj.object_id
            ).order_by('-reverted_on')
            return [
                {
                    "id": r.id,
                    "remarks": r.remarks or "",
                    "reverted_on": r.reverted_on.isoformat() if r.reverted_on else None,
                    "reverted_by": getattr(r.reverted_by, "username", None) or "Joint Commissioner",
                    "stage": getattr(r.stage, "name", None) or "Site Enquiry Officer"
                }
                for r in reverts
            ]
        except Exception:
            return []

    def validate_shop_image_document(self, value):
        validate_uploaded_file(
            value,
            allowed_extensions=['pdf'],
            allowed_mime_types=['application/pdf'],
            max_size_bytes=5 * 1024 * 1024,
            field_label='Shop image document (PDF)'
        )
        return value
