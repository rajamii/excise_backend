from rest_framework import serializers
from .models import (
    HeadOfOrganisation,
    ExciseSecretary
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
