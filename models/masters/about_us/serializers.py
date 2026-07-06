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

    class Meta:
        model = AboutUs
        fields = ['id', 'title', 'content', 'is_active', 'isActive', 'created_at', 'updated_at']
        extra_kwargs = {
            'is_active': {'required': False},
        }

