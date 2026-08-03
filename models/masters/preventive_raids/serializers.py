from rest_framework import serializers
from .models import PreventiveRaid, PreventiveRaidImage
from utils.file_validation import validate_uploaded_file


IMAGE_EXTENSIONS = ('jpg', 'jpeg', 'png', 'webp')
IMAGE_MIME_TYPES = ('image/jpeg', 'image/png', 'image/webp')


class PreventiveRaidImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = PreventiveRaidImage
        fields = ['id', 'image']

    def validate_image(self, value):
        validate_uploaded_file(
            value,
            allowed_extensions=IMAGE_EXTENSIONS,
            allowed_mime_types=IMAGE_MIME_TYPES,
            max_size_bytes=5 * 1024 * 1024,
            field_label='Preventive raid image',
        )
        return value


class PreventiveRaidSerializer(serializers.ModelSerializer):
    images = PreventiveRaidImageSerializer(many=True, read_only=True)

    class Meta:
        model = PreventiveRaid
        fields = ['id', 'title', 'subject', 'date', 'images', 'created_at', 'updated_at']
