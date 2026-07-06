from rest_framework import serializers
from models.masters.core.models import RuralWard, Block


class RuralWardSerializer(serializers.ModelSerializer):
    status = serializers.SerializerMethodField()
    block_name = serializers.CharField(
        source='block.block_name',
        read_only=True
    )
    created_by_username = serializers.CharField(
        source='created_by.username',
        read_only=True
    )

    class Meta:
        model = RuralWard
        fields = [
            'id',
            'ward_name',
            'ward_number',
            'block',
            'block_name',
            'population',
            'area_sq_km',
            'is_active',
            'status',
            'created_by',
            'created_by_username',
            'operation_date',
        ]
        read_only_fields = ['id', 'operation_date', 'created_by']

    def get_status(self, obj):
        return "Active" if obj.is_active else "Inactive"

    def validate_ward_number(self, value):
        if value <= 0:
            raise serializers.ValidationError("Ward number must be positive.")
        return value

    def validate(self, data):
        block = data.get('block')
        ward_number = data.get('ward_number')

        if block and ward_number:
            queryset = RuralWard.objects.filter(
                block=block,
                ward_number=ward_number
            )
            if self.instance:
                queryset = queryset.exclude(pk=self.instance.pk)
            if queryset.exists():
                raise serializers.ValidationError({
                    'ward_number': f'Ward number {ward_number} already exists in this block.'
                })
        return data

    def create(self, validated_data):
        request = self.context.get('request')
        if request and hasattr(request, 'user'):
            validated_data['created_by'] = request.user
        return super().create(validated_data)
