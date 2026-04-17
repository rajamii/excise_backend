from rest_framework import serializers
from .models import Checkpost

class CheckpostSerializer(serializers.ModelSerializer):
    class Meta:
        model = Checkpost
        fields = ['check_post_id', 'check_post_name']
        read_only_fields = ['check_post_id']
