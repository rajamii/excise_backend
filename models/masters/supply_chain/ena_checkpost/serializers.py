from rest_framework import serializers
from .models import Checkpost

class CheckpostSerializer(serializers.ModelSerializer):
    class Meta:
        model = Checkpost
        fields = ['id', 'checkpost_name']
        read_only_fields = ['id']
