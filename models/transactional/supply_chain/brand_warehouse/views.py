from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.db.models import Q, Sum, Count, Avg
from django.utils import timezone
from django.apps import apps
from datetime import datetime, timedelta

from .models import BrandWarehouse, BrandWarehouseUtilization, BrandWarehouseArrival
from .serializers import (
    BrandWarehouseSerializer,
    BrandWarehouseSummarySerializer,
    BrandWarehouseUtilizationSerializer,
    BrandWarehouseArrivalSerializer,
    StockAdjustmentSerializer,
    AllSikkimBrandsSerializer
)
from .production_serializers import (
    ProductionBatchSerializer,
    CreateProductionBatchSerializer
)
from .services import BrandWarehouseStockService
from models.masters.supply_chain.liquor_data.models import LiquorData


class BrandWarehouseViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Brand Warehouse CRUD operations and custom actions
    Ensures ALL Sikkim brands are always shown (no brands go missing)
    """
    queryset = BrandWarehouse.objects.all().select_related('liquor_data').prefetch_related('utilizations', 'arrivals')
    permission_classes = [AllowAny]

    def get_serializer_class(self):
        """Return appropriate serializer based on action"""
        if self.action == 'list':
            return BrandWarehouseSummarySerializer
        elif self.action == 'all_sikkim_brands':
            return AllSikkimBrandsSerializer
        return BrandWarehouseSerializer

    def get_queryset(self):
        """
        Get queryset - returns ALL brands, frontend filtering handles distillery-specific display
        """
        # Return ALL Brand Warehouse entries - frontend will filter by distillery
        queryset = BrandWarehouse.objects.all().select_related('liquor_data').prefetch_related('utilizations', 'arrivals')
        
        # Apply filters from query parameters
        distillery_name = self.request.query_params.get('distillery_name', None)
        if distillery_name:
            queryset = queryset.filter(distillery_name__icontains=distillery_name)
            
        brand_type = self.request.query_params.get('brand_type', None)
        if brand_type:
            queryset = queryset.filter(brand_type=brand_type)
            
        status_filter = self.request.query_params.get('status', None)
        if status_filter:
            queryset = queryset.filter(status=status_filter)
            
        return queryset.order_by('distillery_name', 'brand_details', 'capacity_size')

    def list(self, request, *args, **kwargs):
        """
        List all brands with NEW tags
        Frontend filtering will handle showing only relevant brands for each distillery
        """
        try:
            # Get ALL brand warehouse entries - frontend will filter by distillery
            queryset = BrandWarehouse.objects.all().select_related('liquor_data').prefetch_related('utilizations', 'arrivals')
            
            # Apply any filters from query parameters
            distillery_name = self.request.query_params.get('distillery_name', None)
            if distillery_name:
                queryset = queryset.filter(distillery_name__icontains=distillery_name)
                
            brand_type = self.request.query_params.get('brand_type', None)
            if brand_type:
                queryset = queryset.filter(brand_type=brand_type)
                
            status_filter = self.request.query_params.get('status', None)
            if status_filter:
                queryset = queryset.filter(status=status_filter)
            
            # Order by distillery, then brand name and pack size
            queryset = queryset.order_by('distillery_name', 'brand_details', 'capacity_size')
            
            # Paginate if needed
            page = self.paginate_queryset(queryset)
            if page is not None:
                serializer = self.get_serializer(page, many=True)
                return self.get_paginated_response(serializer.data)
            
            # Serialize all brands
            serializer = self.get_serializer(queryset, many=True)
            
            # Add summary information
            total_brands = queryset.count()
            new_brands_count = sum(1 for brand in queryset if BrandWarehouseStockService.check_if_brand_is_new(brand))
            total_stock = sum(brand.current_stock for brand in queryset)
            
            # Return in the format expected by frontend
            return Response(serializer.data, status=status.HTTP_200_OK)
            
        except Exception as e:
            return Response({
                'success': False,
                'error': str(e),
                'message': 'Error loading brands'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['get'], url_path='test-brands')
    def test_brands(self, request):
        """
        Test endpoint to verify brands are visible
        """
        try:
            # Get all brands (not just Sikkim)
            all_brands = BrandWarehouse.objects.all()
            
            # Get Sikkim brands specifically
            sikkim_brands = BrandWarehouse.objects.filter(
                distillery_name__icontains='sikkim'
            )
            
            return Response({
                'success': True,
                'message': 'Test endpoint working',
                'total_all_brands': all_brands.count(),
                'total_sikkim_brands': sikkim_brands.count(),
                'sample_all_brands': [
                    {
                        'id': brand.id,
                        'brand_name': brand.brand_details,
                        'distillery': brand.distillery_name,
                        'pack_size': f"{brand.capacity_size}ml",
                        'current_stock': brand.current_stock,
                        'status': brand.status
                    }
                    for brand in all_brands[:5]
                ],
                'sample_sikkim_brands': [
                    {
                        'id': brand.id,
                        'brand_name': brand.brand_details,
                        'pack_size': f"{brand.capacity_size}ml",
                        'current_stock': brand.current_stock,
                        'status': brand.status
                    }
                    for brand in sikkim_brands[:5]
                ]
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            return Response({
                'success': False,
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['get'], url_path='all-sikkim-brands')
    def all_sikkim_brands(self, request):
        """
        Get ALL Sikkim brands with NEW tags (ensures no brands go missing)
        """
        try:
            # This method ensures ALL Sikkim brands are shown
            serializer = AllSikkimBrandsSerializer()
            data = serializer.to_representation(None)
            
            return Response({
                'success': True,
                **data
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            return Response({
                'success': False,
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=['get'], url_path='brand-details')
    def get_brand_details(self, request, pk=None):
        """
        Get detailed brand information including stock, arrivals, and utilization
        This is used for the Brand Details modal with tabs
        """
        brand_warehouse = self.get_object()
        
        # Get recent arrivals (last 20)
        recent_arrivals = BrandWarehouseStockService.get_arrival_history(brand_warehouse.id, 20)
        arrival_summary = BrandWarehouseStockService.get_arrival_summary(brand_warehouse.id, 30)
        
        # Get recent utilizations (last 10)
        recent_utilizations = brand_warehouse.utilizations.all()[:10]
        
        # Serialize data
        arrivals_data = BrandWarehouseArrivalSerializer(recent_arrivals, many=True).data
        utilizations_data = BrandWarehouseUtilizationSerializer(recent_utilizations, many=True).data
        
        # Calculate additional metrics
        total_arrivals_30_days = arrival_summary['total_quantity_added']
        total_utilizations_30_days = brand_warehouse.utilizations.filter(
            date__gte=timezone.now().date() - timedelta(days=30)
        ).aggregate(total=Sum('quantity'))['total'] or 0
        
        # Check if brand is new
        is_new = BrandWarehouseStockService.check_if_brand_is_new(brand_warehouse)
        
        return Response({
            'success': True,
            'brand_details': {
                'id': brand_warehouse.id,
                'distillery_name': brand_warehouse.distillery_name,
                'brand_name': brand_warehouse.brand_details,
                'brand_type': brand_warehouse.brand_type,
                'pack_size': f"{brand_warehouse.capacity_size}ml",
                'last_updated': brand_warehouse.updated_at,
                'is_new': is_new,
            },
            'stock_information': {
                'current_stock': brand_warehouse.current_stock,
                'max_capacity': brand_warehouse.max_capacity,
                'reorder_level': brand_warehouse.reorder_level,
                'utilization_percentage': brand_warehouse.utilization_percentage,
                'status': brand_warehouse.status,
                'status_display': brand_warehouse.get_status_display(),
            },
            'pack_size_details': {
                'capacity_ml': brand_warehouse.capacity_size,
                'current_stock': brand_warehouse.current_stock,
                'max_capacity': brand_warehouse.max_capacity,
                'utilization_percentage': brand_warehouse.utilization_percentage,
            },
            'arrivals_tab': {
                'recent_arrivals': arrivals_data,
                'summary_30_days': {
                    'total_arrivals': arrival_summary['total_arrivals'],
                    'total_quantity': arrival_summary['total_quantity_added'],
                    'average_per_arrival': arrival_summary['average_per_arrival'],
                },
                'total_count': len(arrivals_data)
            },
            'utilizations_tab': {
                'recent_utilizations': utilizations_data,
                'total_30_days': total_utilizations_30_days,
                'total_count': len(utilizations_data)
            }
        }, status=status.HTTP_200_OK)

    @action(detail=True, methods=['get'], url_path='arrivals')
    def get_arrivals(self, request, pk=None):
        """
        Get arrival history for a brand warehouse entry
        """
        brand_warehouse = self.get_object()
        
        # Get query parameters
        limit = int(request.query_params.get('limit', 50))
        days = int(request.query_params.get('days', 30))
        
        # Get arrivals
        arrivals = BrandWarehouseStockService.get_arrival_history(brand_warehouse.id, limit)
        arrival_summary = BrandWarehouseStockService.get_arrival_summary(brand_warehouse.id, days)
        
        # Serialize arrivals
        serializer = BrandWarehouseArrivalSerializer(arrivals, many=True)
        
        return Response({
            'success': True,
            'arrivals': serializer.data,
            'summary': arrival_summary,
            'total_count': arrivals.count() if hasattr(arrivals, 'count') else len(arrivals)
        }, status=status.HTTP_200_OK)

    @action(detail=True, methods=['get'], url_path='production-history')
    def get_production_history(self, request, pk=None):
        """
        Get production history for a specific brand warehouse
        """
        brand_warehouse = self.get_object()
        from .production_models import ProductionBatch
        
        # Get query parameters
        limit = int(request.query_params.get('limit', 20))
        days = int(request.query_params.get('days', 30))
        
        # Get production batches
        production_batches = ProductionBatch.objects.filter(
            brand_warehouse=brand_warehouse,
            production_date__gte=timezone.now().date() - timedelta(days=days)
        ).order_by('-production_date', '-production_time')[:limit]
        
        # Calculate summary
        total_production = production_batches.aggregate(
            total_quantity=Sum('quantity_produced'),
            total_batches=Count('id'),
            avg_batch_size=Avg('quantity_produced')
        )
        
        # Serialize data
        serializer = ProductionBatchSerializer(production_batches, many=True)
        
        return Response({
            'success': True,
            'productionHistory': serializer.data,
            'summary': {
                'totalQuantity': total_production['total_quantity'] or 0,
                'totalBatches': total_production['total_batches'] or 0,
                'averageBatchSize': float(total_production['avg_batch_size'] or 0),
                'periodDays': days
            },
            'brandInfo': {
                'brandName': brand_warehouse.brand_details,
                'packSize': f"{brand_warehouse.capacity_size}ml",
                'currentStock': brand_warehouse.current_stock
            }
        }, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='add-production')
    def add_production(self, request, pk=None):
        """
        Add a new production batch for a brand warehouse
        """
        brand_warehouse = self.get_object()
        from .production_models import ProductionBatch
        
        # Prepare data
        data = request.data.copy()
        data['brand_warehouse_id'] = brand_warehouse.id
        
        # Auto-generate batch reference if not provided
        if not data.get('batch_reference'):
            today = timezone.now().date()
            existing_count = ProductionBatch.objects.filter(
                brand_warehouse=brand_warehouse,
                production_date=today
            ).count()
            data['batch_reference'] = f"PROD-{today.strftime('%Y%m%d')}-{brand_warehouse.id:03d}-{existing_count + 1:03d}"
        
        # Create serializer
        serializer = CreateProductionBatchSerializer(data=data)
        
        if serializer.is_valid():
            production_batch = serializer.save()
            
            # Return created batch data
            response_serializer = ProductionBatchSerializer(production_batch)
            
            return Response({
                'success': True,
                'message': 'Production batch added successfully',
                'production_batch': response_serializer.data,
                'updated_stock': {
                    'previous_stock': production_batch.stock_before,
                    'new_stock': production_batch.stock_after,
                    'quantity_added': production_batch.quantity_produced
                }
            }, status=status.HTTP_201_CREATED)
        
        return Response({
            'success': False,
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['get'], url_path='production-summary')
    def get_production_summary(self, request):
        """
        Get overall production summary for all Sikkim brands
        """
        from .production_models import ProductionBatch
        
        # Get date range
        days = int(request.query_params.get('days', 30))
        start_date = timezone.now().date() - timedelta(days=days)
        
        # Get Sikkim brand warehouses
        sikkim_warehouses = BrandWarehouse.objects.filter(
            distillery_name__icontains='sikkim'
        )
        
        # Get production data
        production_data = ProductionBatch.objects.filter(
            brand_warehouse__in=sikkim_warehouses,
            production_date__gte=start_date
        ).aggregate(
            total_batches=Count('id'),
            total_quantity=Sum('quantity_produced'),
            avg_batch_size=Avg('quantity_produced')
        )
        
        # Get today's production
        today_production = ProductionBatch.objects.filter(
            brand_warehouse__in=sikkim_warehouses,
            production_date=timezone.now().date()
        ).aggregate(
            today_quantity=Sum('quantity_produced'),
            today_batches=Count('id')
        )
        
        # Get this week's production
        week_start = timezone.now().date() - timedelta(days=timezone.now().weekday())
        week_production = ProductionBatch.objects.filter(
            brand_warehouse__in=sikkim_warehouses,
            production_date__gte=week_start
        ).aggregate(
            week_quantity=Sum('quantity_produced'),
            week_batches=Count('id')
        )
        
        # Get this month's production
        month_start = timezone.now().date().replace(day=1)
        month_production = ProductionBatch.objects.filter(
            brand_warehouse__in=sikkim_warehouses,
            production_date__gte=month_start
        ).aggregate(
            month_quantity=Sum('quantity_produced'),
            month_batches=Count('id')
        )
        
        # Get last production date
        last_production = ProductionBatch.objects.filter(
            brand_warehouse__in=sikkim_warehouses
        ).order_by('-production_date', '-production_time').first()
        
        return Response({
            'success': True,
            'summary': {
                'total_batches': production_data['total_batches'] or 0,
                'total_quantity': production_data['total_quantity'] or 0,
                'average_batch_size': float(production_data['avg_batch_size'] or 0),
                'today_production': today_production['today_quantity'] or 0,
                'today_batches': today_production['today_batches'] or 0,
                'week_production': week_production['week_quantity'] or 0,
                'week_batches': week_production['week_batches'] or 0,
                'month_production': month_production['month_quantity'] or 0,
                'month_batches': month_production['month_batches'] or 0,
                'last_production_date': last_production.production_date if last_production else None,
                'period_days': days
            }
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'], url_path='initialize-all-brands')
    def initialize_all_brands(self, request):
        """
        Initialize ALL Sikkim brands from LiquorData
        This ensures no brands go missing
        """
        try:
            # Get all Sikkim brands and create warehouse entries
            all_brands = BrandWarehouseStockService.get_all_sikkim_brands_with_stock()
            
            return Response({
                'success': True,
                'message': f'Initialized {all_brands.count()} Sikkim brands',
                'total_brands': all_brands.count()
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            return Response({
                'success': False,
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['post'], url_path='sync-production-stock')
    def sync_production_stock(self, request):
        """
        Manually sync production batches with brand warehouse stock
        This fixes any inconsistencies between production records and stock levels
        """
        try:
            # Get parameters
            brand_id = request.data.get('brand_id')
            days = int(request.data.get('days', 30))
            
            # Perform sync
            sync_results = BrandWarehouseStockService.sync_production_with_stock(
                brand_warehouse_id=brand_id,
                days=days
            )
            
            return Response({
                'success': True,
                'message': 'Production stock sync completed',
                'results': sync_results
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            return Response({
                'success': False,
                'error': str(e),
                'message': 'Error during production stock sync'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def destroy(self, request, *args, **kwargs):
        """
        Override destroy to prevent accidental deletion
        Require confirmation and use soft delete
        """
        instance = self.get_object()
        
        # Check for confirmation parameter
        confirm_delete = request.data.get('confirm_delete', False)
        if not confirm_delete:
            return Response({
                'success': False,
                'error': 'Deletion requires confirmation',
                'message': 'Brand warehouse deletion requires explicit confirmation to prevent accidental data loss.',
                'required_parameter': 'confirm_delete: true',
                'warning': 'This action will soft delete the brand warehouse entry. Stock data will be preserved.'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Get user information
        deleted_by = getattr(request.user, 'username', 'anonymous') if hasattr(request, 'user') else 'system'
        
        try:
            # Perform soft delete instead of hard delete
            instance.soft_delete(deleted_by=deleted_by)
            
            return Response({
                'success': True,
                'message': f'Brand warehouse "{instance.brand_details}" has been soft deleted',
                'deleted_at': instance.deleted_at,
                'deleted_by': instance.deleted_by,
                'note': 'This entry can be restored if needed. Contact administrator for restoration.'
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            return Response({
                'success': False,
                'error': str(e),
                'message': 'Error during soft deletion'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=['post'], url_path='restore')
    def restore_deleted(self, request, pk=None):
        """
        Restore a soft deleted brand warehouse entry
        """
        try:
            # Get the instance including soft deleted ones
            instance = BrandWarehouse.objects.all_with_deleted().get(pk=pk)
            
            if not instance.is_deleted:
                return Response({
                    'success': False,
                    'message': 'This brand warehouse entry is not deleted'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Restore the entry
            instance.restore()
            
            return Response({
                'success': True,
                'message': f'Brand warehouse "{instance.brand_details}" has been restored',
                'restored_at': timezone.now()
            }, status=status.HTTP_200_OK)
            
        except BrandWarehouse.DoesNotExist:
            return Response({
                'success': False,
                'error': 'Brand warehouse entry not found'
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({
                'success': False,
                'error': str(e),
                'message': 'Error during restoration'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['get'], url_path='deleted-entries')
    def get_deleted_entries(self, request):
        """
        Get all soft deleted brand warehouse entries
        """
        try:
            deleted_entries = BrandWarehouse.objects.deleted_only().order_by('-deleted_at')
            
            # Serialize the deleted entries
            serializer = BrandWarehouseSerializer(deleted_entries, many=True)
            
            return Response({
                'success': True,
                'deleted_entries': serializer.data,
                'total_count': deleted_entries.count(),
                'message': 'These entries can be restored if needed'
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
    permission_classes = [AllowAny]

    def get_queryset(self):
        """Filter queryset based on query parameters"""
        queryset = BrandWarehouseUtilization.objects.all().select_related('brand_warehouse')
        
        # Filter by brand warehouse
        brand_warehouse_id = self.request.query_params.get('brand_warehouse', None)
        if brand_warehouse_id:
            queryset = queryset.filter(brand_warehouse_id=brand_warehouse_id)
            
        # Filter by status
        status_filter = self.request.query_params.get('status', None)
        if status_filter:
            queryset = queryset.filter(status=status_filter)
            
        return queryset.order_by('-date')


class ProductionBatchViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Production Batch CRUD operations
    """
    serializer_class = ProductionBatchSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        from .production_models import ProductionBatch
        return ProductionBatch.objects.all().select_related('brand_warehouse')

    def get_serializer_class(self):
        """Return appropriate serializer based on action"""
        if self.action == 'create':
            return CreateProductionBatchSerializer
        return ProductionBatchSerializer

    def filter_queryset(self, queryset):
        """Filter queryset based on query parameters"""
        # Filter by brand warehouse
        brand_warehouse_id = self.request.query_params.get('brand_warehouse', None)
        if brand_warehouse_id:
            queryset = queryset.filter(brand_warehouse_id=brand_warehouse_id)
            
        # Filter by date range
        date_from = self.request.query_params.get('date_from', None)
        if date_from:
            queryset = queryset.filter(production_date__gte=date_from)
            
        date_to = self.request.query_params.get('date_to', None)
        if date_to:
            queryset = queryset.filter(production_date__lte=date_to)
            
        # Filter by status
        status_filter = self.request.query_params.get('status', None)
        if status_filter:
            queryset = queryset.filter(status=status_filter)
            
        return queryset.order_by('-production_date', '-production_time')

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'], url_path='daily-summary')
    def daily_summary(self, request):
        """
        Get daily production summary
        """
        from .production_models import ProductionBatch
        
        # Get date parameter or default to today
        date_str = request.query_params.get('date', timezone.now().date().isoformat())
        try:
            target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            return Response({
                'success': False,
                'error': 'Invalid date format. Use YYYY-MM-DD'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Get production batches for the date
        daily_batches = ProductionBatch.objects.filter(
            production_date=target_date
        ).select_related('brand_warehouse')
        
        # Calculate summary
        summary_data = daily_batches.aggregate(
            total_quantity=Sum('quantity_produced'),
            batch_count=Count('id')
        )
        
        # Get unique brands and managers
        brands_produced = list(daily_batches.values_list(
            'brand_warehouse__brand_details', flat=True
        ).distinct())
        
        managers = list(daily_batches.values_list(
            'production_manager', flat=True
        ).distinct())
        
        reference_numbers = list(daily_batches.values_list(
            'batch_reference', flat=True
        ))
        
        return Response({
            'success': True,
            'date': target_date,
            'summary': {
                'total_quantity': summary_data['total_quantity'] or 0,
                'batch_count': summary_data['batch_count'] or 0,
                'brands_produced': brands_produced,
                'production_managers': managers,
                'reference_numbers': reference_numbers
            },
            'batches': ProductionBatchSerializer(daily_batches, many=True).data
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'], url_path='brand-production')
    def brand_production(self, request):
        """
        Get production data for a specific brand
        """
        from .production_models import ProductionBatch
        
        brand_warehouse_id = request.query_params.get('brand_warehouse_id')
        if not brand_warehouse_id:
            return Response({
                'success': False,
                'error': 'brand_warehouse_id parameter is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            brand_warehouse = BrandWarehouse.objects.get(id=brand_warehouse_id)
        except BrandWarehouse.DoesNotExist:
            return Response({
                'success': False,
                'error': 'Brand warehouse not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Get date range
        days = int(request.query_params.get('days', 30))
        start_date = timezone.now().date() - timedelta(days=days)
        
        # Get production batches
        production_batches = ProductionBatch.objects.filter(
            brand_warehouse=brand_warehouse,
            production_date__gte=start_date
        ).order_by('-production_date', '-production_time')
        
        # Calculate summary
        summary_data = production_batches.aggregate(
            total_quantity=Sum('quantity_produced'),
            total_batches=Count('id'),
            avg_batch_size=Avg('quantity_produced')
        )
        
        return Response({
            'success': True,
            'brandInfo': {
                'id': brand_warehouse.id,
                'brandName': brand_warehouse.brand_details,
                'packSize': f"{brand_warehouse.capacity_size}ml",
                'currentStock': brand_warehouse.current_stock
            },
            'summary': {
                'totalQuantity': summary_data['total_quantity'] or 0,
                'totalBatches': summary_data['total_batches'] or 0,
                'averageBatchSize': float(summary_data['avg_batch_size'] or 0),
                'periodDays': days
            },
            'productionHistory': ProductionBatchSerializer(production_batches, many=True).data
        }, status=status.HTTP_200_OK)