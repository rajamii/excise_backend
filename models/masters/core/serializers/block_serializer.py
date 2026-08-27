from rest_framework import serializers
from models.masters.core.models import Block, LocationSubcategory


class BlockSerializer(serializers.ModelSerializer):
    status = serializers.SerializerMethodField()
    subcategory_name = serializers.CharField(
        source='subcategory.subcategory_name',
        read_only=True
    )
    subcategoryName = serializers.CharField(
        source='subcategory.subcategory_name',
        read_only=True
    )
    created_by_username = serializers.CharField(
        source='created_by.username',
        read_only=True
    )
    gpu_name = serializers.CharField(required=False)
    gpuName = serializers.CharField(source='gpu_name', required=False)
    block_name = serializers.CharField(source='gpu_name', required=False)
    blockName = serializers.CharField(source='gpu_name', required=False)
    is_active = serializers.BooleanField(required=False, default=True)
    isActive = serializers.BooleanField(source='is_active', required=False, default=True)

    class Meta:
        model = Block
        fields = [
            'id',
            'gpu_name',
            'gpuName',
            'block_name',
            'blockName',
            'subcategory',
            'subcategory_name',
            'subcategoryName',
            'is_active',
            'isActive',
            'status',
            'created_by',
            'created_by_username',
            'operation_date',
        ]
        read_only_fields = ['id', 'operation_date', 'created_by']

    def get_status(self, obj):
        return "Active" if obj.is_active else "Inactive"

    def to_internal_value(self, data):
        data = data.copy() if hasattr(data, 'copy') else dict(data)
        name_val = (
            data.get('gpu_name') or
            data.get('gpuName') or
            data.get('block_name') or
            data.get('blockName')
        )
        if name_val:
            data['gpu_name'] = name_val
            data['gpuName'] = name_val
            data['block_name'] = name_val
            data['blockName'] = name_val

        active_val = data.get('is_active') if 'is_active' in data else data.get('isActive')
        if active_val is not None:
            data['is_active'] = active_val
            data['isActive'] = active_val

        return super().to_internal_value(data)

    def validate(self, attrs):
        if not attrs.get('gpu_name'):
            raise serializers.ValidationError({'gpu_name': ['This field is required.']})
        return attrs

    def create(self, validated_data):
        request = self.context.get('request')
        if request and hasattr(request, 'user'):
            validated_data['created_by'] = request.user
        return super().create(validated_data)
