from rest_framework import serializers
from .models import UserActivity

class UserActivitySerializer(serializers.ModelSerializer):
    activity_type_display = serializers.CharField(
        source='get_activity_type_display',
        read_only=True
    )
    email = serializers.EmailField(source='user.email', read_only=True)

    class Meta:
        model = UserActivity
        fields = [
            'id',
            'email',
            'activity_type',
            'activity_type_display',
            'ip_address',
            'location',
            'timestamp',
            'metadata'
        ]
        read_only_fields = fields
