from rest_framework import serializers
from .models import UserActivity

class UserActivitySerializer(serializers.ModelSerializer):
    activity_type_display = serializers.CharField(
        source='get_activity_type_display',
        read_only=True
    )
    user_id = serializers.IntegerField(source='user.id', read_only=True)
    username = serializers.CharField(source='user.username', read_only=True)
    email = serializers.EmailField(source='user.email', read_only=True)
    role = serializers.CharField(source='user.role.name', read_only=True)

    target_user_id = serializers.IntegerField(source='target_user.id', read_only=True)
    target_username = serializers.CharField(source='target_user.username', read_only=True)
    target_email = serializers.EmailField(source='target_user.email', read_only=True)

    class Meta:
        model = UserActivity
        fields = [
            'id',
            'user_id',
            'username',
            'email',
            'role',
            'target_user_id',
            'target_username',
            'target_email',
            'activity_type',
            'activity_type_display',
            'ip_address',
            'user_agent',
            'device_id',
            'location',
            'timestamp',
            'metadata'
        ]
        read_only_fields = fields


from .models import AdminLog

class AdminLogSerializer(serializers.ModelSerializer):
    timestamp_formatted = serializers.SerializerMethodField()

    class Meta:
        model = AdminLog
        fields = [
            'id',
            'admin_id',
            'username',
            'full_name',
            'role',
            'user',
            'module_name',
            'application_id',
            'content_type',
            'object_id',
            'action',
            'from_stage',
            'to_stage',
            'to_stage_name',
            'to_stage_username',
            'status',
            'remarks',

            'reverted_by_id',
            'reverted_by_username',
            'reverted_by_name',
            'reverted_by_role',
            'reverted_to_id',
            'reverted_to_username',
            'reverted_to_name',
            'reverted_to_role',
            'reverted_to_stage',
            'ip_address',
            'user_agent',
            'metadata',
            'timestamp',
            'timestamp_formatted',
        ]
        read_only_fields = ['id', 'timestamp', 'timestamp_formatted']

    def get_timestamp_formatted(self, obj):
        if obj.timestamp:
            return obj.timestamp.strftime("%d-%m-%Y %I:%M:%S %p")
        return None

