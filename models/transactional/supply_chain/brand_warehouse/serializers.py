from rest_framework import serializers
from .models import BrandWarehouse, BrandWarehouseUtilization, BrandWarehouseArrival, BrandWarehouseTpCancellation
from .services import BrandWarehouseStockService
from models.masters.supply_chain.liquor_data.models import LiquorData


class BrandWarehouseArrivalSerializer(serializers.ModelSerializer):
    """
    Serializer for Brand Warehouse Arrival records
    """
    source_type_display = serializers.CharField(source='get_source_type_display', read_only=True)
    
    class Meta:
        model = BrandWarehouseArrival
        fields = [
            'id',
            'reference_no',
            'source_type',
            'source_type_display',
            'quantity_added',
            'previous_stock',
            'new_stock',
            'arrival_date',
            'notes',
            'created_at',
        ]
        read_only_fields = ['id', 'created_at']


class BrandWarehouseTpCancellationSerializer(serializers.ModelSerializer):
    """
    Serializer for Brand Warehouse TP Cancellation records
    """
    class Meta:
        model = BrandWarehouseTpCancellation
        fields = '__all__'


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
    Serializer for Brand Warehouse main model with NEW tag support
    """
    total_capacity = serializers.ReadOnlyField()
    total_utilized = serializers.ReadOnlyField()
    utilization_percentage = serializers.ReadOnlyField()
    utilizations = BrandWarehouseUtilizationSerializer(many=True, read_only=True)
    arrivals = BrandWarehouseArrivalSerializer(many=True, read_only=True)
    recent_arrivals = serializers.SerializerMethodField()
    is_new = serializers.SerializerMethodField()
    last_arrival_date = serializers.SerializerMethodField()
    
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
            'arrivals',
            'recent_arrivals',
            'is_new',
            'last_arrival_date',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'total_capacity',
            'total_utilized',
            'utilization_percentage',
            'arrivals',
            'recent_arrivals',
            'is_new',
            'last_arrival_date',
            'created_at',
            'updated_at',
        ]

    def get_recent_arrivals(self, obj):
        """Get recent arrivals (last 10)"""
        recent = obj.arrivals.all()[:10]
        return BrandWarehouseArrivalSerializer(recent, many=True).data

    def get_is_new(self, obj):
        """Check if brand has recent stock updates (NEW tag)"""
        return BrandWarehouseStockService.check_if_brand_is_new(obj, days=7)

    def get_last_arrival_date(self, obj):
        """Get the date of the last arrival"""
        last_arrival = obj.arrivals.first()
        return last_arrival.arrival_date if last_arrival else None

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


class StockAdjustmentSerializer(serializers.Serializer):
    """
    Serializer for manual stock adjustments
    """
    ADJUSTMENT_TYPE_CHOICES = [
        ('ADD', 'Add Stock'),
        ('SUBTRACT', 'Subtract Stock'),
    ]
    
    adjustment_type = serializers.ChoiceField(choices=ADJUSTMENT_TYPE_CHOICES)
    quantity = serializers.IntegerField(min_value=1)
    reason = serializers.CharField(max_length=500)
    
    def validate(self, data):
        """Validate stock adjustment"""
        brand_warehouse = self.context.get('brand_warehouse')
        adjustment_type = data.get('adjustment_type')
        quantity = data.get('quantity')
        
        if adjustment_type == 'SUBTRACT' and brand_warehouse:
            if quantity > brand_warehouse.current_stock:
                raise serializers.ValidationError({
                    'quantity': f'Cannot subtract {quantity} units. Current stock: {brand_warehouse.current_stock}'
                })
        
        return data


class BrandWarehouseSummarySerializer(serializers.ModelSerializer):
    """
    Lightweight serializer for listing ALL Sikkim brands with NEW tags
    """
    total_capacity = serializers.ReadOnlyField()
    total_utilized = serializers.ReadOnlyField()
    utilization_percentage = serializers.ReadOnlyField()
    utilization_count = serializers.SerializerMethodField()
    is_new = serializers.SerializerMethodField()
    last_arrival_date = serializers.SerializerMethodField()
    pack_sizes_info = serializers.SerializerMethodField()
    
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
            'is_new',
            'last_arrival_date',
            'pack_sizes_info',
            'updated_at',
        ]

    def get_utilization_count(self, obj):
        """Get count of utilization records"""
        return obj.utilizations.count()

    def get_is_new(self, obj):
        """Check if brand has recent stock updates (NEW tag)"""
        return BrandWarehouseStockService.check_if_brand_is_new(obj, days=7)

    def get_last_arrival_date(self, obj):
        """Get the date of the last arrival"""
        last_arrival = obj.arrivals.first()
        return last_arrival.arrival_date if last_arrival else None

    def get_pack_sizes_info(self, obj):
        """Get pack size information for this brand"""
        return {
            'capacity_ml': obj.capacity_size,
            'current_stock': obj.current_stock,
            'max_capacity': obj.max_capacity,
            'status': obj.status,
            'utilization_percentage': obj.utilization_percentage
        }


class AllSikkimBrandsSerializer(serializers.Serializer):
    """
    Serializer for returning ALL Sikkim brands (ensures no brands go missing)
    """
    def to_representation(self, instance):
        """
        Custom representation to show all Sikkim brands with NEW tags
        """
        # Get all Sikkim brands (this ensures no brands are missing)
        all_brands = BrandWarehouseStockService.get_all_sikkim_brands_with_stock()
        
        # Get brands with NEW tags
        brands_with_tags = BrandWarehouseStockService.get_brands_with_new_tags()
        
        # Serialize all brands
        serialized_brands = []
        for brand in all_brands:
            brand_data = BrandWarehouseSummarySerializer(brand).data
            
            # Add NEW tag information
            tag_info = brands_with_tags.get(brand.id, {})
            brand_data['is_new'] = tag_info.get('is_new', False)
            brand_data['last_arrival'] = tag_info.get('last_arrival')
            
            serialized_brands.append(brand_data)
        
        return {
            'total_brands': len(serialized_brands),
            'brands': serialized_brands,
            'summary': {
                'total_stock': sum(b['current_stock'] for b in serialized_brands),
                'new_brands_count': sum(1 for b in serialized_brands if b['is_new']),
                'out_of_stock_count': sum(1 for b in serialized_brands if b['status'] == 'OUT_OF_STOCK'),
                'in_stock_count': sum(1 for b in serialized_brands if b['status'] == 'IN_STOCK'),
            }
        }