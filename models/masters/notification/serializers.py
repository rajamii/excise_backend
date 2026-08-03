from django.urls import reverse
from rest_framework import serializers

from .models import Notification
from utils.file_validation import validate_uploaded_file

MAX_NOTIFICATION_FILE_SIZE = 2 * 1024 * 1024


# Serializer for Notification model
# Used for serializing/deserializing public notifications
class NotificationSerializer(serializers.ModelSerializer):
    status = serializers.SerializerMethodField()
    notification_file_url = serializers.SerializerMethodField()
    notification_file_download_url = serializers.SerializerMethodField()

    class Meta:
        model = Notification
        fields = [
            'id',
            'subject',
            'category',
            'notification_date',
            'notification_file',
            'notification_file_url',
            'notification_file_download_url',
            'is_active',
            'status',
        ]

    def get_status(self, obj):
        return "Active" if obj.is_active else "Inactive"

    def validate_notification_file(self, value):
        validate_uploaded_file(
            value,
            allowed_extensions=['jpeg', 'jpg', 'pdf'],
            allowed_mime_types=['image/jpeg', 'application/pdf'],
            max_size_bytes=MAX_NOTIFICATION_FILE_SIZE,
            field_label='Notification file'
        )
        return value

    def get_notification_file_url(self, obj):
        if not obj.notification_file:
            return None
        request = self.context.get('request')
        if request:
            return request.build_absolute_uri(obj.notification_file.url)
        return obj.notification_file.url

    def get_notification_file_download_url(self, obj):
        if not obj.notification_file:
            return None
        request = self.context.get('request')
        path = reverse('notification:notification-download', kwargs={'pk': obj.pk})
        if request:
            return request.build_absolute_uri(path)
        return path
