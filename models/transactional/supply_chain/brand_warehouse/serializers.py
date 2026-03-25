from rest_framework import serializers
from .models import BrandWarehouse, BrandWarehouseUtilization, BrandWarehouseArrival, BrandWarehouseTpCancellation
from .services import BrandWarehouseStockService
from models.masters.supply_chain.liquor_data.models import MasterLiquorCategory


class BrandWarehouseArrivalSerializer(serializers.ModelSerializer):
    """
    Serializer for Brand Warehouse Arrival records
    """
    source_type_display = serializers.CharField(source='get_source_type_display', read_only=True)
    
    class Meta:
        model = BrandWarehouseArrival
        fields = [
            'id',
            'license_id',
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
    bottles_reversed = serializers.IntegerField(source='quantity_bottles', read_only=True)
    permit_no = serializers.CharField(source='reference_no', read_only=True)
    remarks = serializers.CharField(source='reason', read_only=True)
    previousStock = serializers.IntegerField(source='previous_stock', read_only=True)
    newStock = serializers.IntegerField(source='new_stock', read_only=True)
    cancelled_by_display = serializers.SerializerMethodField()

    def get_cancelled_by_display(self, obj):
        """Return stored cancelled_by value (full name stored directly in DB)."""
        return obj.cancelled_by or ''

    class Meta:
        model = BrandWarehouseTpCancellation
        fields = [
            'id', 'brand_warehouse', 'reference_no', 'permit_no',
            'cancellation_date', 'cancelled_by', 'cancelled_by_display', 'quantity_cases',
            'quantity_bottles', 'bottles_reversed', 'amount_refunded',
            'reason', 'remarks', 'previous_stock', 'previousStock',
            'new_stock', 'newStock', 'permit_date', 'destination',
            'vehicle_no', 'depot_address', 'brand_name'
        ]


class BrandWarehouseUtilizationSerializer(serializers.ModelSerializer):
    """
    Serializer for Brand Warehouse Utilization records
    """
    previousStock = serializers.IntegerField(source='previous_stock', read_only=True)
    newStock = serializers.IntegerField(source='new_stock', read_only=True)
    approved_by_display = serializers.SerializerMethodField()

    def get_approved_by_display(self, obj):
        """Return stored approved_by value (full name stored directly in DB)."""
        return obj.approved_by or ''

    class Meta:
        model = BrandWarehouseUtilization
        fields = [
            'id',
            'brand_warehouse',
            'license_id',
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
            'approved_by_display',
            'approval_date',
            'previousStock',
            'newStock',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'total_bottles', 'previousStock', 'newStock', 'approved_by_display']

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
    brand_type = serializers.CharField(read_only=True)
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

    # Keep API backward-compatible: expose `capacity_size` as ml while DB stores FK id.
    capacity_size = serializers.IntegerField(required=False, allow_null=True)
    capacity_size_id = serializers.IntegerField(read_only=True)
    capacity_size_master_id = serializers.IntegerField(write_only=True, required=False, allow_null=True)

    class Meta:
        model = BrandWarehouse
        fields = [
            'id',
            'is_sync',
            'license_id',
            'distillery_name',
            'liquor_type',
            'brand_type',
            'brand_details',
            'current_stock',
            'capacity_size',
            'capacity_size_id',
            'capacity_size_master_id',
            'total_capacity',
            'status',
            'liquor_data_id',
            'liquor_data_details',
            'ex_factory_price_rs_per_case',
            'excise_duty_rs_per_case',
            'education_cess_rs_per_case',
            'additional_excise_duty_rs_per_case',
            'additional_excise_duty_12_5_percent_rs_per_case',
            'mrp_rs_per_bottle',
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
            'is_sync',
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
        """Backward-compatible structure built from brand_warehouse columns."""
        return {
            'id': obj.liquor_data_id,
            'brand_name': obj.brand_details,
            'brand_owner': '',
            'liquor_type': obj.brand_type,
            'pack_size_ml': int(obj.capacity_size) if getattr(obj, 'capacity_size_id', None) else 0,
            'manufacturing_unit_name': obj.distillery_name,
            'ex_factory_price_rs_per_case': obj.ex_factory_price_rs_per_case,
            'excise_duty_rs_per_case': obj.excise_duty_rs_per_case,
            'education_cess_rs_per_case': obj.education_cess_rs_per_case,
            'additional_excise_duty_rs_per_case': obj.additional_excise_duty_rs_per_case,
            'additional_excise_duty_12_5_percent_rs_per_case': obj.additional_excise_duty_12_5_percent_rs_per_case,
            'mrp_rs_per_bottle': obj.mrp_rs_per_bottle,
        }

    def validate_current_stock(self, value):
        """Validate that current stock is not negative"""
        if value < 0:
            raise serializers.ValidationError("Current stock cannot be negative")
        return value

    def validate(self, data):
        """Validate capacity and stock levels"""
        capacity_size_ml = data.get('capacity_size', None)
        master_id = data.pop('capacity_size_master_id', None)

        if master_id is not None:
            try:
                data['capacity_size'] = MasterLiquorCategory.objects.get(id=int(master_id))
            except (TypeError, ValueError, MasterLiquorCategory.DoesNotExist):
                raise serializers.ValidationError({'capacity_size_master_id': 'Invalid capacity size master id'})
            return data

        if capacity_size_ml is None:
            return data

        if int(capacity_size_ml) < 0:
            raise serializers.ValidationError("Capacity size cannot be negative")

        category, _ = MasterLiquorCategory.objects.get_or_create(size_ml=int(capacity_size_ml))
        data['capacity_size'] = category
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
    brand_type = serializers.CharField(read_only=True)
    total_capacity = serializers.ReadOnlyField()
    total_utilized = serializers.ReadOnlyField()
    utilization_percentage = serializers.ReadOnlyField()
    utilization_count = serializers.SerializerMethodField()
    is_new = serializers.SerializerMethodField()
    last_arrival_date = serializers.SerializerMethodField()
    pack_sizes_info = serializers.SerializerMethodField()

    capacity_size = serializers.IntegerField(required=False, allow_null=True)
    capacity_size_id = serializers.IntegerField(read_only=True)
    
    class Meta:
        model = BrandWarehouse
        fields = [
            'id',
            'is_sync',
            'license_id',
            'distillery_name',
            'liquor_type',
            'brand_type',
            'brand_details',
            'current_stock',
            'capacity_size',
            'capacity_size_id',
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
        read_only_fields = ['id', 'is_sync']

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
        capacity_ml = int(obj.capacity_size) if getattr(obj, 'capacity_size_id', None) else 0
        return {
            'capacity_ml': capacity_ml,
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
