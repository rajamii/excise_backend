from rest_framework import serializers
from django.apps import apps


class ProductionBatchSerializer(serializers.ModelSerializer):
    """
    Serializer for Production Batch model
    """
    brand_name = serializers.CharField(source='brand_warehouse.brand_details', read_only=True)
    pack_size = serializers.CharField(source='brand_warehouse.capacity_size', read_only=True)
    production_datetime = serializers.DateTimeField(read_only=True)
    formatted_reference = serializers.CharField(read_only=True)

    class Meta:
        model = 'brand_warehouse.ProductionBatch'
        fields = [
            'id',
            'batch_reference',
            'production_date',
            'production_time',
            'production_datetime',
            'formatted_reference',
            'quantity_produced',
            'stock_before',
            'stock_after',
            'production_manager',
            'approved_by',
            'status',
            'notes',
            'brand_name',
            'pack_size',
            'created_at',
            'updated_at'
        ]
        read_only_fields = ['id', 'stock_before', 'stock_after', 'created_at', 'updated_at']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Get the actual model class
        self.Meta.model = apps.get_model('brand_warehouse', 'ProductionBatch')

    def validate_quantity_produced(self, value):
        """Validate that quantity produced is positive"""
        if value <= 0:
            raise serializers.ValidationError("Quantity produced must be greater than 0")
        return value

    def validate_batch_reference(self, value):
        """Validate that batch reference is unique"""
        ProductionBatch = apps.get_model('brand_warehouse', 'ProductionBatch')
        if self.instance:
            # For updates, exclude current instance
            if ProductionBatch.objects.exclude(pk=self.instance.pk).filter(batch_reference=value).exists():
                raise serializers.ValidationError("Batch reference must be unique")
        else:
            # For new instances
            if ProductionBatch.objects.filter(batch_reference=value).exists():
                raise serializers.ValidationError("Batch reference must be unique")
        return value


class CreateProductionBatchSerializer(serializers.ModelSerializer):
    """
    Serializer for creating new production batches
    """
    brand_warehouse_id = serializers.IntegerField(write_only=True)

    class Meta:
        model = 'brand_warehouse.ProductionBatch'
        fields = [
            'brand_warehouse_id',
            'batch_reference',
            'production_date',
            'production_time',
            'quantity_produced',
            'production_manager',
            'approved_by',
            'notes'
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Get the actual model class
        self.Meta.model = apps.get_model('brand_warehouse', 'ProductionBatch')

    def validate_brand_warehouse_id(self, value):
        """Validate that brand warehouse exists"""
        BrandWarehouse = apps.get_model('brand_warehouse', 'BrandWarehouse')
        try:
            BrandWarehouse.objects.get(id=value)
        except BrandWarehouse.DoesNotExist:
            raise serializers.ValidationError("Brand warehouse not found")
        return value

    def create(self, validated_data):
        """Create production batch and update stock"""
        BrandWarehouse = apps.get_model('brand_warehouse', 'BrandWarehouse')
        ProductionBatch = apps.get_model('brand_warehouse', 'ProductionBatch')
        
        brand_warehouse_id = validated_data.pop('brand_warehouse_id')
        brand_warehouse = BrandWarehouse.objects.get(id=brand_warehouse_id)
        
        production_batch = ProductionBatch.objects.create(
            brand_warehouse=brand_warehouse,
            **validated_data
        )
        
        return production_batch