from rest_framework import serializers
from models.masters.core.models import LocationSubcategory, LocationCategory


class LocationSubcategorySerializer(serializers.ModelSerializer):
    """
    Serializer for LocationSubcategory model.
    """
    # Computed fields
    status = serializers.SerializerMethodField()
    category_name = serializers.CharField(
        source='category.category_name',
        read_only=True
    )
    created_by_username = serializers.CharField(
        source='created_by.username',
        read_only=True
    )

    class Meta:
        model = LocationSubcategory
        fields = [
            'id',
            'subcategory_name',
            'category',
            'category_name',
            'description',
            'is_active',
            'status',
            'created_by',
            'created_by_username',
            'operation_date',
        ]
        read_only_fields = ['id', 'operation_date', 'created_by']

    def get_status(self, obj):
        """Return status string based on is_active field"""
        return "Active" if obj.is_active else "Inactive"

    def validate(self, data):
        """
        Validate that the subcategory name is unique within its category.
        """
        category = data.get('category')
        subcategory_name = data.get('subcategory_name', '').strip()

        if category and subcategory_name:
            queryset = LocationSubcategory.objects.filter(
                category=category,
                subcategory_name__iexact=subcategory_name
            )
            
            # During updates, exclude current instance
            if self.instance:
                queryset = queryset.exclude(pk=self.instance.pk)
            
            if queryset.exists():
                raise serializers.ValidationError({
                    'subcategory_name': f'A subcategory with this name already exists under "{category.category_name}".'
                })

        return data

    def validate_subcategory_name(self, value):
        """Normalize and validate subcategory name"""
        return value.strip()

    def create(self, validated_data):
        """Custom create with audit logging"""
        request = self.context.get('request')
        if request and hasattr(request, 'user'):
            validated_data['created_by'] = request.user
        return super().create(validated_data)
