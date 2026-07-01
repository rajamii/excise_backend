from rest_framework import serializers
from models.transactional.site_enquiry.models import SiteEnquiryReport
from utils.file_validation import validate_uploaded_file


class SiteEnquiryReportSerializer(serializers.ModelSerializer):
    application_id = serializers.CharField(source='content_object.application_id', read_only=True)
    application_type = serializers.CharField(source='content_type.model', read_only=True)
    # Backward-compatible aliases used by some frontend screens.
    site_enquiry_is_reverted = serializers.BooleanField(source='is_reverted', read_only=True)
    revertedRemarks = serializers.CharField(source='reverted_remarks', read_only=True)

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
        ]

    def validate_shop_image_document(self, value):
        validate_uploaded_file(
            value,
            field_name='shop_image_document',
            label='Shop image document',
            allowed_extensions={'.pdf', '.jpg', '.jpeg', '.png'},
            allowed_content_types={'application/pdf', 'image/jpeg', 'image/png', 'image/jpg'},
            max_size_mb=10,
        )
        return value
