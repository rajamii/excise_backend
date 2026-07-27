from pathlib import Path

from django.urls import reverse
from rest_framework import serializers

from .models import Notification

MAX_NOTIFICATION_FILE_SIZE = 2 * 1024 * 1024
ALLOWED_NOTIFICATION_FILE_EXTENSIONS = {'.jpeg', '.jpg', '.pdf'}
ALLOWED_NOTIFICATION_CONTENT_TYPES = {'image/jpeg', 'application/pdf'}


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
        if not value:
            return value

        extension = Path(value.name).suffix.lower()
        content_type = getattr(value, 'content_type', '')

        if value.size > MAX_NOTIFICATION_FILE_SIZE:
            raise serializers.ValidationError('File size must be less than 2 MB.')

        if extension not in ALLOWED_NOTIFICATION_FILE_EXTENSIONS:
            raise serializers.ValidationError('Only JPEG, JPG, or PDF files are allowed.')

        if content_type and content_type not in ALLOWED_NOTIFICATION_CONTENT_TYPES:
            raise serializers.ValidationError('Only JPEG, JPG, or PDF files are allowed.')

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
