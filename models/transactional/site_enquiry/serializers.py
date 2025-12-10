from rest_framework import serializers
from models.transactional.site_enquiry.models import SiteEnquiryReport


class SiteEnquiryReportSerializer(serializers.ModelSerializer):
    application_id = serializers.CharField(source='content_object.application_id', read_only=True)
    application_type = serializers.CharField(source='content_type.model', read_only=True)

    class Meta:
        model = SiteEnquiryReport
        fields = '__all__'
        read_only_fields = ['created_at', 'updated_at', 'application_id', 'application_type']