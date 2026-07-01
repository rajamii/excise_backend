from rest_framework import serializers
from .models import (
    HeadOfOrganisation,
    ExciseSecretary
)
from utils.file_validation import validate_uploaded_file


# Serializer for HeadOfOrganisation model
# Used for serializing/deserializing About Us head details
class HeadOfOrganisationSerializer(serializers.ModelSerializer):
    class Meta:
        model = HeadOfOrganisation
        fields = '__all__'

    def validate_image(self, value):
        validate_uploaded_file(
            value,
            field_name='image',
            label='Profile image',
            allowed_extensions={'.jpg', '.jpeg', '.png'},
            allowed_content_types={'image/jpeg', 'image/png', 'image/jpg'},
            max_size_mb=5,
        )
        return value


# Serializer for ExciseSecretary model
# Used for serializing/deserializing Excise Secretaries / Principal Secretaries
class ExciseSecretarySerializer(serializers.ModelSerializer):
    class Meta:
        model = ExciseSecretary
        fields = '__all__'
