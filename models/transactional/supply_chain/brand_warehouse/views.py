from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.db.models import Q, Sum, Count
from django.utils import timezone
from datetime import datetime, timedelta

from .models import BrandWarehouse, BrandWarehouseUtilization
from .serializers import (
    BrandWarehouseSerializer,
    BrandWarehouseSummarySerializer,
    BrandWarehouseUtilizationSerializer,
    StockAdjustmentSerializer
)
from models.masters.supply_chain.liquor_data.models import LiquorData


class BrandWarehouseViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Brand Warehouse CRUD operations and custom actions
    """
    queryset = BrandWarehouse.objects.all().select_related('liquor_data').prefetch_related('utilizations')
    permission_classes = [AllowAny]

    def get_serializer_class(self):
        """Return appropriate serializer based on action"""
        if self.action == 'list':
            return BrandWarehouseSummarySerializer
        return BrandWarehouseSerializer

    def get_queryset(self):
        """Filter queryset based on query parameters"""
        queryset = BrandWarehouse.objects.all().select_related('liquor_data').prefetch_related('utilizations')
        
        # Filter by distillery name
        distillery_name = self.request.query_params.get('distillery_name', None)
        if distillery_name:
            queryset = queryset.filter(distillery_name__icontains=distillery_name)
            
        # Filter by brand type
        brand_type = self.request.query_params.get('brand_type', None)
        if brand_type:
            queryset = queryset.filter(brand_type=brand_type)
            
        # Filter by status
        status_filter = self.request.query_params.get('status', None)
        if status_filter:
            queryset = queryset.filter(status=status_filter)
            
        # Filter by stock level (custom logic would be needed or just naive filter)
        # Assuming frontend passes simpler filters or we handle complex logic elsewhere
        
        return queryset

    @action(detail=False, methods=['post'], url_path='initialize-sikkim-brands')
    def initialize_sikkim_brands(self, request):
        """
        Initialize brand warehouse entries for ALL brands from liquor_data_details table.
        Creates one entry per Brand + Pack Size combination.
        """
        try:
            # Fetch all LiquorData entries, we need distinct brand + distillery + pack_size
            # We fetch all to map them accurately
            liquor_data_query = LiquorData.objects.values(
                'id',
                'brand_name', 
                'manufacturing_unit_name', 
                'brand_owner', 
                'liquor_type',
                'pack_size_ml'
            )
            
            created_count = 0
            updated_count = 0
            errors = []
            
            # Group by composite key to ensure uniqueness in BrandWarehouse
            # Key: (distillery, brand_name, pack_size)
            processed_keys = set()
            
            for item in liquor_data_query:
                brand_name = item['brand_name']
                distillery = item['manufacturing_unit_name']
                pack_size = item['pack_size_ml']
                
                if not brand_name or not distillery or not pack_size:
                    continue
                
                # Create a unique key for this batch
                key = (distillery, brand_name, pack_size)
                if key in processed_keys:
                    continue
                processed_keys.add(key)
                
                try:
                    # Create or update warehouse entry
                    # One entry per Brand + Pack Size
                    warehouse_entry, created = BrandWarehouse.objects.get_or_create(
                        distillery_name=distillery,
                        brand_details__icontains=brand_name,
                        capacity_size=pack_size,
                        defaults={
                            'brand_type': item['liquor_type'] or 'Unknown',
                            'brand_details': f"{brand_name} - {item['brand_owner']}",
                            'current_stock': 0,
                            'max_capacity': 10000, # Default capacity
                            'reorder_level': 1000,
                            'average_daily_usage': 0,
                            'status': 'OUT_OF_STOCK',
                            'liquor_data_id': item['id'] # Link to source
                        }
                    )
                    
                    if not created:
                        # Update if exists
                        warehouse_entry.brand_details = f"{brand_name} - {item['brand_owner']}"
                        warehouse_entry.liquor_data_id = item['id']
                        warehouse_entry.save(update_fields=['brand_details', 'liquor_data'])
                        updated_count += 1
                    else:
                        created_count += 1
                        
                except Exception as e:
                    errors.append({
                        'brand': f"{brand_name} ({pack_size}ml)",
                        'error': str(e)
                    })
            
            return Response({
                'success': True,
                'message': 'Brand warehouse initialized successfully',
                'created': created_count,
                'updated': updated_count,
                'total_processed': len(liquor_data_query),
                'errors': errors if errors else None
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            return Response({
                'success': False,
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=['post'], url_path='add-utilization')
    def add_utilization(self, request, pk=None):
        """
        Add a utilization record (transit permit) to a brand warehouse entry
        """
        brand_warehouse = self.get_object()
        
        serializer = BrandWarehouseUtilizationSerializer(
            data=request.data,
            context={'request': request}
        )
        
        if serializer.is_valid():
            # Set the brand_warehouse for this utilization
            serializer.save(brand_warehouse=brand_warehouse)
            
            return Response({
                'success': True,
                'message': 'Utilization record added successfully',
                'data': serializer.data
            }, status=status.HTTP_201_CREATED)
        
        return Response({
            'success': False,
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'], url_path='adjust-stock')
    def adjust_stock(self, request, pk=None):
        """
        Adjust stock for a brand warehouse entry
        """
        brand_warehouse = self.get_object()
        
        serializer = StockAdjustmentSerializer(
            data=request.data,
            context={'brand_warehouse': brand_warehouse}
        )
        
        if serializer.is_valid():
            adjustment_type = serializer.validated_data['adjustment_type']
            quantity = serializer.validated_data['quantity']
            reason = serializer.validated_data['reason']
            
            # Store previous stock
            previous_stock = brand_warehouse.current_stock
            
            # Adjust stock
            if adjustment_type == 'ADD':
                brand_warehouse.current_stock += quantity
            else:  # SUBTRACT
                brand_warehouse.current_stock = max(0, brand_warehouse.current_stock - quantity)
            
            # Update status
            brand_warehouse.update_status()
            
            return Response({
                'success': True,
                'message': 'Stock adjusted successfully',
                'data': {
                    'previous_stock': previous_stock,
                    'new_stock': brand_warehouse.current_stock,
                    'adjustment_type': adjustment_type,
                    'quantity': quantity,
                    'reason': reason,
                    'status': brand_warehouse.status
                }
            }, status=status.HTTP_200_OK)
        
        return Response({
            'success': False,
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['get'], url_path='grouped')
    def get_grouped_brands(self, request):
        """
        Get brands grouped by brand name with all pack sizes and their stock levels
        """
        try:
            # Get all brand warehouse entries
            queryset = self.get_queryset()
            
            # Group by brand name (extracted from brand_details)
            grouped_brands = {}
            
            for item in queryset:
                # Extract brand name from brand_details
                brand_name = item.brand_details.split(' - ')[0].strip() if item.brand_details else item.distillery_name
                
                if brand_name not in grouped_brands:
                    grouped_brands[brand_name] = {
                        'brandName': brand_name,
                        'distilleryName': item.distillery_name,
                        'brandType': item.brand_type,
                        'packSizes': {},
                        'totalStock': 0,
                        'totalCapacity': 0,
                        'totalUtilized': 0,
                        'lastUpdated': item.updated_at,
                        'overallStatus': 'OUT_OF_STOCK'
                    }
                
                # Add pack size information
                pack_size = item.capacity_size
                grouped_brands[brand_name]['packSizes'][pack_size] = {
                    'id': item.id,
                    'capacitySize': pack_size,
                    'currentStock': item.current_stock,
                    'maxCapacity': item.max_capacity,
                    'status': item.status,
                    'totalUtilized': item.total_utilized,
                    'reorderLevel': item.reorder_level,
                    'utilizationPercentage': item.utilization_percentage
                }
                
                # Update totals
                grouped_brands[brand_name]['totalStock'] += item.current_stock
                grouped_brands[brand_name]['totalCapacity'] += item.max_capacity
                grouped_brands[brand_name]['totalUtilized'] += item.total_utilized
                
                # Update overall status (if any pack size is in stock, brand is in stock)
                if item.status == 'IN_STOCK':
                    grouped_brands[brand_name]['overallStatus'] = 'IN_STOCK'
                elif item.status == 'LOW_STOCK' and grouped_brands[brand_name]['overallStatus'] == 'OUT_OF_STOCK':
                    grouped_brands[brand_name]['overallStatus'] = 'LOW_STOCK'
                
                # Update last updated time
                if item.updated_at > grouped_brands[brand_name]['lastUpdated']:
                    grouped_brands[brand_name]['lastUpdated'] = item.updated_at
            
            # Convert to list and sort pack sizes
            result = []
            for brand_data in grouped_brands.values():
                # Sort pack sizes
                brand_data['packSizes'] = dict(sorted(brand_data['packSizes'].items()))
                result.append(brand_data)
            
            # Sort by brand name
            result.sort(key=lambda x: x['brandName'])
            
            return Response(result, status=status.HTTP_200_OK)
            
        except Exception as e:
            return Response({
                'success': False,
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['get'], url_path='overview')
    def get_warehouse_overview(self, request):
        """
        Get warehouse overview statistics for dashboard
        """
        try:
            total_brands = BrandWarehouse.objects.count()
            
            # Calculate totals
            totals = BrandWarehouse.objects.aggregate(
                total_capacity=Sum('max_capacity'),
                total_current_stock=Sum('current_stock'),
            )
            
            # Status counts
            status_counts = BrandWarehouse.objects.values('status').annotate(
                count=Count('id')
            )
            
            low_stock_alerts = next((item['count'] for item in status_counts if item['status'] == 'LOW_STOCK'), 0)
            out_of_stock_alerts = next((item['count'] for item in status_counts if item['status'] == 'OUT_OF_STOCK'), 0)
            
            # Today's statistics
            today = timezone.now().date()
            today_updated = BrandWarehouse.objects.filter(
                updated_at__date=today
            ).count()
            
            # Calculate total utilized today (from utilizations created today)
            today_utilizations = BrandWarehouseUtilization.objects.filter(
                created_at__date=today,
                status__in=['APPROVED', 'IN_TRANSIT', 'DELIVERED']
            ).aggregate(
                total=Sum('quantity')
            )
            today_consumption = today_utilizations['total'] or 0
            
            # Pending adjustments (can be customized based on your business logic)
            pending_permits = BrandWarehouseUtilization.objects.filter(
                status='PENDING'
            ).count()
            
            return Response({
                'totalBrands': total_brands,
                'totalCapacity': totals['total_capacity'] or 0,
                'totalCurrentStock': totals['total_current_stock'] or 0,
                'lowStockAlerts': low_stock_alerts,
                'outOfStockAlerts': out_of_stock_alerts,
                'newArrivals': today_updated,
                'todayProduction': 0,  # Can be calculated from production entries
                'todayConsumption': today_consumption,
                'pendingAdjustments': pending_permits,
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            return Response({
                'success': False,
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class BrandWarehouseUtilizationViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Brand Warehouse Utilization CRUD operations
    """
    queryset = BrandWarehouseUtilization.objects.all().select_related('brand_warehouse')
    serializer_class = BrandWarehouseUtilizationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Filter queryset based on query parameters"""
        queryset = super().get_queryset()
        
        # Filter by brand warehouse
        brand_warehouse_id = self.request.query_params.get('brand_warehouse', None)
        if brand_warehouse_id:
            queryset = queryset.filter(brand_warehouse_id=brand_warehouse_id)
        
        # Filter by status
        status_filter = self.request.query_params.get('status', None)
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        # Filter by date range
        date_from = self.request.query_params.get('date_from', None)
        date_to = self.request.query_params.get('date_to', None)
        
        if date_from:
            queryset = queryset.filter(date__gte=date_from)
        if date_to:
            queryset = queryset.filter(date__lte=date_to)
        
        return queryset

    @action(detail=True, methods=['post'], url_path='approve')
    def approve_utilization(self, request, pk=None):
        """
        Approve a utilization record
        """
        utilization = self.get_object()
        
        approved_by = request.data.get('approved_by', 'System')
        
        utilization.status = 'APPROVED'
        utilization.approved_by = approved_by
        utilization.approval_date = timezone.now()
        utilization.save()
        
        serializer = self.get_serializer(utilization)
        
        return Response({
            'success': True,
            'message': 'Utilization approved successfully',
            'data': serializer.data
        }, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='cancel')
    def cancel_utilization(self, request, pk=None):
        """
        Cancel a utilization record
        """
        utilization = self.get_object()
        
        old_status = utilization.status
        utilization.status = 'CANCELLED'
        utilization.save()
        
        # If it was previously approved/in-transit/delivered, restore the stock
        if old_status in ['APPROVED', 'IN_TRANSIT', 'DELIVERED']:
            utilization.brand_warehouse.current_stock += utilization.quantity
            utilization.brand_warehouse.update_status()
        
        serializer = self.get_serializer(utilization)
        
        return Response({
            'success': True,
            'message': 'Utilization cancelled successfully',
            'data': serializer.data
        }, status=status.HTTP_200_OK)
