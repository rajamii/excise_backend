from rest_framework import serializers
from .models import BrandWarehouse, BrandWarehouseUtilization
from models.masters.supply_chain.liquor_data.models import LiquorData


class BrandWarehouseUtilizationSerializer(serializers.ModelSerializer):
    """
    Serializer for Brand Warehouse Utilization records
    """
    total_bottles = serializers.ReadOnlyField()

    class Meta:
        model = BrandWarehouseUtilization
        fields = [
            'id',
            'brand_warehouse',
            'permit_no',
            'date',
            'distributor',
            'depot_address',
            'vehicle',
            'quantity',
            'cases',
            'bottles_per_case',
            'total_bottles',
            'status',
            'approved_by',
            'approval_date',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'total_bottles']

    def validate_quantity(self, value):
        """Validate that quantity is positive"""
        if value <= 0:
            raise serializers.ValidationError("Quantity must be greater than 0")
        return value

    def validate(self, data):
        """Validate utilization data"""
        # Check if brand warehouse has sufficient stock
        brand_warehouse = data.get('brand_warehouse')
        quantity = data.get('quantity', 0)
        
        if brand_warehouse and quantity > brand_warehouse.current_stock:
            raise serializers.ValidationError({
                'quantity': f'Insufficient stock. Available: {brand_warehouse.current_stock} units'
            })
        
        return data


class BrandWarehouseSerializer(serializers.ModelSerializer):
    """
    Serializer for Brand Warehouse main model
    """
    total_capacity = serializers.ReadOnlyField()
    total_utilized = serializers.ReadOnlyField()
    utilization_percentage = serializers.ReadOnlyField()
    utilizations = BrandWarehouseUtilizationSerializer(many=True, read_only=True)
    
    # Liquor data details (read-only for display)
    liquor_data_details = serializers.SerializerMethodField()

    class Meta:
        model = BrandWarehouse
        fields = [
            'id',
            'distillery_name',
            'brand_type',
            'brand_details',
            'current_stock',
            'capacity_size',
            'total_capacity',
            'status',
            'liquor_data',
            'liquor_data_details',
            'reorder_level',
            'max_capacity',
            'average_daily_usage',
            'total_utilized',
            'utilization_percentage',
            'utilizations',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'total_capacity',
            'total_utilized',
            'utilization_percentage',
            'created_at',
            'updated_at',
        ]

    def get_liquor_data_details(self, obj):
        """Get liquor data details if linked"""
        if obj.liquor_data:
            return {
                'id': obj.liquor_data.id,
                'brand_name': obj.liquor_data.brand_name,
                'brand_owner': obj.liquor_data.brand_owner,
                'liquor_type': obj.liquor_data.liquor_type,
                'pack_size_ml': obj.liquor_data.pack_size_ml,
                'manufacturing_unit_name': obj.liquor_data.manufacturing_unit_name,
            }
        return None

    def validate_current_stock(self, value):
        """Validate that current stock is not negative"""
        if value < 0:
            raise serializers.ValidationError("Current stock cannot be negative")
        return value

    def validate(self, data):
        """Validate capacity and stock levels"""
        capacity_size = data.get('capacity_size', 0)
        
        if capacity_size < 0:
            raise serializers.ValidationError("Capacity size cannot be negative")
        
        return data


class BrandWarehouseSummarySerializer(serializers.ModelSerializer):
    """
    Lightweight serializer for listing brand warehouses without nested data
    """
    total_capacity = serializers.ReadOnlyField()
    total_utilized = serializers.ReadOnlyField()
    utilization_percentage = serializers.ReadOnlyField()
    utilization_count = serializers.SerializerMethodField()
    
    class Meta:
        model = BrandWarehouse
        fields = [
            'id',
            'distillery_name',
            'brand_type',
            'brand_details',
            'current_stock',
            'capacity_size',
            'total_capacity',
            'status',
            'total_utilized',
            'utilization_percentage',
            'utilization_count',
            'updated_at',
        ]

    def get_utilization_count(self, obj):
        """Get count of utilization records"""
        return obj.utilizations.count()


class StockAdjustmentSerializer(serializers.Serializer):
    """
    Serializer for stock adjustment operations
    """
    adjustment_type = serializers.ChoiceField(choices=['ADD', 'SUBTRACT'])
    quantity = serializers.IntegerField(min_value=1)
    reason = serializers.CharField(max_length=500)

    def validate(self, data):
        """Validate stock adjustment"""
        brand_warehouse = self.context.get('brand_warehouse')
        adjustment_type = data.get('adjustment_type')
        quantity = data.get('quantity')
        
        if adjustment_type == 'SUBTRACT' and quantity > brand_warehouse.current_stock:
            raise serializers.ValidationError({
                'quantity': f'Cannot subtract {quantity}. Current stock: {brand_warehouse.current_stock}'
            })
        
        return data
