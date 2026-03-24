from rest_framework import serializers
from models.masters.core.models import LocationCategory


class LocationCategorySerializer(serializers.ModelSerializer):
    """
    Serializer for LocationCategory model.
    """
    # Computed fields
    status = serializers.SerializerMethodField()
    created_by_username = serializers.CharField(
        source='created_by.username',
        read_only=True
    )
    subcategory_count = serializers.SerializerMethodField()

    class Meta:
        model = LocationCategory
        fields = [
            'id',
            'category_name',
            'description',
            'is_active',
            'status',
            'subcategory_count',
            'created_by',
            'created_by_username',
            'operation_date',
        ]
        read_only_fields = ['id', 'operation_date', 'created_by']

    def get_status(self, obj):
        """Return status string based on is_active field"""
        return "Active" if obj.is_active else "Inactive"

    def get_subcategory_count(self, obj):
        """Return count of active subcategories"""
        return obj.subcategories.filter(is_active=True).count()

    def validate_category_name(self, value):
        """Validate category name is unique (case insensitive)"""
        value = value.strip()
        
        queryset = LocationCategory.objects.filter(
            category_name__iexact=value
        )
        
        # During updates, exclude current instance
        if self.instance:
            queryset = queryset.exclude(pk=self.instance.pk)
        
        if queryset.exists():
            raise serializers.ValidationError(
                "A location category with this name already exists."
            )
        
        return value

    def create(self, validated_data):
        """Custom create with audit logging"""
        request = self.context.get('request')
        if request and hasattr(request, 'user'):
            validated_data['created_by'] = request.user
        return super().create(validated_data)
