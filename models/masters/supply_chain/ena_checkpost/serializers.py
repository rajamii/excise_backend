from rest_framework import serializers
from .models import Checkpost

class CheckpostSerializer(serializers.ModelSerializer):
    class Meta:
        model = Checkpost
        fields = ['check_post_id', 'check_post_name', 'is_active', 'created_at', 'updated_at']
        read_only_fields = ['check_post_id', 'created_at', 'updated_at']
