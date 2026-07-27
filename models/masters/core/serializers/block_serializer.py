from rest_framework import serializers
from models.masters.core.models import Block, LocationSubcategory


class BlockSerializer(serializers.ModelSerializer):
    status = serializers.SerializerMethodField()
    subcategory_name = serializers.CharField(
        source='subcategory.subcategory_name',
        read_only=True
    )
    created_by_username = serializers.CharField(
        source='created_by.username',
        read_only=True
    )

    class Meta:
        model = Block
        fields = [
            'id',
            'block_name',
            'subcategory',
            'subcategory_name',
            'is_active',
            'status',
            'created_by',
            'created_by_username',
            'operation_date',
        ]
        read_only_fields = ['id', 'operation_date', 'created_by']

    def get_status(self, obj):
        return "Active" if obj.is_active else "Inactive"

    def create(self, validated_data):
        request = self.context.get('request')
        if request and hasattr(request, 'user'):
            validated_data['created_by'] = request.user
        return super().create(validated_data)
