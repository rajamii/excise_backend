from rest_framework import serializers
from .models import (
    HeadOfOrganisation,
    ExciseSecretary,
    AboutUs
)


# Serializer for HeadOfOrganisation model
# Used for serializing/deserializing About Us head details
class HeadOfOrganisationSerializer(serializers.ModelSerializer):
    class Meta:
        model = HeadOfOrganisation
        fields = '__all__'


# Serializer for ExciseSecretary model
# Used for serializing/deserializing Excise Secretaries / Principal Secretaries
class ExciseSecretarySerializer(serializers.ModelSerializer):
    class Meta:
        model = ExciseSecretary
        fields = '__all__'


class AboutUsSerializer(serializers.ModelSerializer):
    isActive = serializers.BooleanField(source='is_active', required=False)

    class Meta:
        model = AboutUs
        fields = ['id', 'title', 'content', 'is_active', 'isActive', 'created_at', 'updated_at']
        extra_kwargs = {
            'is_active': {'required': False},
        }

