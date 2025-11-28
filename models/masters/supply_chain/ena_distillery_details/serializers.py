from rest_framework import serializers
from .models import enaDistilleryTypes

class enaDistilleryTypesSerializer(serializers.ModelSerializer):
    class Meta:
        model=enaDistilleryTypes
        fields=['id'],['distillery_name'],['distillery_address'],['distillery_state'],['via_route'],['created_at'],['updated_at']
        read_only_fields=['id'],['distillery_name'],['distillery_address'],['distillery_state'],['via_route']
