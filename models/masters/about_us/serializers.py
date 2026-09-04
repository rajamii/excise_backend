from rest_framework import serializers
from .models import (
    HeadOfOrganisation,
    ExciseSecretary,
    AboutUs,
    Department,
    ProductsServices,
    RefundCancellationPolicy
)
from utils.file_validation import validate_uploaded_file


IMAGE_EXTENSIONS = ('jpg', 'jpeg', 'png', 'webp')
IMAGE_MIME_TYPES = ('image/jpeg', 'image/png', 'image/webp')


# Serializer for HeadOfOrganisation model
# Used for serializing/deserializing About Us head details
class HeadOfOrganisationSerializer(serializers.ModelSerializer):
    class Meta:
        model = HeadOfOrganisation
        fields = '__all__'

    def validate_image(self, value):
        validate_uploaded_file(
            value,
            allowed_extensions=IMAGE_EXTENSIONS,
            allowed_mime_types=IMAGE_MIME_TYPES,
            max_size_bytes=2 * 1024 * 1024,
            field_label='Head of Organisation image',
        )
        return value


# Serializer for ExciseSecretary model
# Used for serializing/deserializing Excise Secretaries / Principal Secretaries
class ExciseSecretarySerializer(serializers.ModelSerializer):
    from_date = serializers.DateField(required=False, allow_null=True)
    to_date = serializers.DateField(required=False, allow_null=True)

    class Meta:
        model = ExciseSecretary
        fields = '__all__'

    def validate_from_date(self, value):
        return value or None

    def validate_to_date(self, value):
        return value or None

    def to_internal_value(self, data):
        # Convert empty string to None for date fields before validation
        mutable = data.copy() if hasattr(data, 'copy') else dict(data)
        for field in ('from_date', 'to_date'):
            if mutable.get(field) == '':
                mutable[field] = None
        return super().to_internal_value(mutable)


class AboutUsSerializer(serializers.ModelSerializer):
    isActive = serializers.BooleanField(source='is_active', required=False)
    pageKey = serializers.CharField(source='page_key', required=False)
    headerColor = serializers.CharField(source='header_color', required=False, allow_blank=True)
    headerTextColor = serializers.CharField(source='header_text_color', required=False, allow_blank=True)
    cardBgColor = serializers.CharField(source='card_bg_color', required=False, allow_blank=True)
    accentColor = serializers.CharField(source='accent_color', required=False, allow_blank=True)

    class Meta:
        model = AboutUs
        fields = [
            'id', 'title', 'content', 'page_key', 'pageKey',
            'header_color', 'headerColor',
            'header_text_color', 'headerTextColor',
            'card_bg_color', 'cardBgColor',
            'accent_color', 'accentColor',
            'is_active', 'isActive', 'created_at', 'updated_at'
        ]
        extra_kwargs = {
            'is_active': {'required': False},
            'page_key': {'required': False},
            'header_color': {'required': False},
            'header_text_color': {'required': False},
            'card_bg_color': {'required': False},
            'accent_color': {'required': False},
        }


class DepartmentSerializer(serializers.ModelSerializer):
    isActive = serializers.BooleanField(source='is_active', required=False)
    headerColor = serializers.CharField(source='header_color', required=False, allow_blank=True)
    headerTextColor = serializers.CharField(source='header_text_color', required=False, allow_blank=True)
    cardBgColor = serializers.CharField(source='card_bg_color', required=False, allow_blank=True)
    accentColor = serializers.CharField(source='accent_color', required=False, allow_blank=True)

    class Meta:
        model = Department
        fields = [
            'id', 'title', 'content',
            'header_color', 'headerColor',
            'header_text_color', 'headerTextColor',
            'card_bg_color', 'cardBgColor',
            'accent_color', 'accentColor',
            'is_active', 'isActive', 'created_at', 'updated_at'
        ]
        extra_kwargs = {
            'is_active': {'required': False},
            'header_color': {'required': False},
            'header_text_color': {'required': False},
            'card_bg_color': {'required': False},
            'accent_color': {'required': False},
        }


class ProductsServicesSerializer(serializers.ModelSerializer):
    isActive = serializers.BooleanField(source='is_active', required=False)
    headerColor = serializers.CharField(source='header_color', required=False, allow_blank=True)
    headerTextColor = serializers.CharField(source='header_text_color', required=False, allow_blank=True)
    cardBgColor = serializers.CharField(source='card_bg_color', required=False, allow_blank=True)
    accentColor = serializers.CharField(source='accent_color', required=False, allow_blank=True)

    class Meta:
        model = ProductsServices
        fields = [
            'id', 'title', 'content',
            'header_color', 'headerColor',
            'header_text_color', 'headerTextColor',
            'card_bg_color', 'cardBgColor',
            'accent_color', 'accentColor',
            'is_active', 'isActive', 'created_at', 'updated_at'
        ]
        extra_kwargs = {
            'is_active': {'required': False},
            'header_color': {'required': False},
            'header_text_color': {'required': False},
            'card_bg_color': {'required': False},
            'accent_color': {'required': False},
        }


class RefundCancellationPolicySerializer(serializers.ModelSerializer):
    isActive = serializers.BooleanField(source='is_active', required=False)
    headerColor = serializers.CharField(source='header_color', required=False, allow_blank=True)
    headerTextColor = serializers.CharField(source='header_text_color', required=False, allow_blank=True)
    cardBgColor = serializers.CharField(source='card_bg_color', required=False, allow_blank=True)
    accentColor = serializers.CharField(source='accent_color', required=False, allow_blank=True)

    class Meta:
        model = RefundCancellationPolicy
        fields = [
            'id', 'title', 'content',
            'header_color', 'headerColor',
            'header_text_color', 'headerTextColor',
            'card_bg_color', 'cardBgColor',
            'accent_color', 'accentColor',
            'is_active', 'isActive', 'created_at', 'updated_at'
        ]
        extra_kwargs = {
            'is_active': {'required': False},
            'header_color': {'required': False},
            'header_text_color': {'required': False},
            'card_bg_color': {'required': False},
            'accent_color': {'required': False},
        }


