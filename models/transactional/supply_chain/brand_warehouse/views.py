from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Sum, Count, Avg, Q
from django.utils import timezone
from datetime import datetime, timedelta

from .models import BrandWarehouse, BrandWarehouseUtilization, BrandWarehouseTpCancellation
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
from .production_models import ProductionBatch
from .services import BrandWarehouseStockService


def _normalize_role_token(role_name: str) -> str:
    return ''.join(ch for ch in str(role_name or '').lower() if ch.isalnum())


def _is_unscoped_admin(user) -> bool:
    # Keep global inventory visibility only for explicit admin-level identities.
    # `is_staff` is too broad in this project and can include scoped business users.
    if bool(getattr(user, 'is_superuser', False)):
        return True

    role_name = _normalize_role_token(getattr(getattr(user, 'role', None), 'name', ''))
    # Roles that should retain cross-license visibility.
    return role_name in {
        'siteadmin',
        'singlewindow',
        'commissioner',
        'jointcommissioner',
        'secretary',
        'permitsection',
        'itcell',
        'districtuser',
        'subenquiryofficer',
    }


def _get_oic_assignment(user):
    try:
        return getattr(user, 'oic_assignment', None)
    except Exception:
        return None


def _expand_license_aliases(license_id: str):
    normalized = str(license_id or '').strip()
    if not normalized:
        return []

    aliases = [normalized]
    if normalized.startswith('NLI/'):
        aliases.append(f"NA/{normalized[4:]}")
    elif normalized.startswith('NA/'):
        aliases.append(f"NLI/{normalized[3:]}")
    return aliases


def _collect_user_license_ids(user):
    """
    Collect all license identifiers that can scope this user in brand_warehouse.
    Includes profile/history IDs, issued license IDs, and NA/NLI aliases.
    """
    scoped_ids = []
    seen = set()

    def _append(value):
        for alias in _expand_license_aliases(value):
            if alias and alias not in seen:
                seen.add(alias)
                scoped_ids.append(alias)

    assignment = _get_oic_assignment(user)
    _append(getattr(getattr(assignment, 'approved_application', None), 'application_id', ''))
    _append(getattr(getattr(assignment, 'license', None), 'license_id', ''))
    _append(getattr(assignment, 'licensee_id', '') or getattr(assignment, 'license_id', ''))

    units = getattr(user, 'manufacturing_units', None)
    if units is not None:
        for unit_licensee_id in (
            units.exclude(licensee_id__isnull=True)
            .exclude(licensee_id='')
            .order_by('-updated_at', '-id')
            .values_list('licensee_id', flat=True)
        ):
            _append(unit_licensee_id)

    licenses = getattr(user, 'licenses', None)
    if licenses is not None:
        today = timezone.now().date()

        for source_object_id in (
            licenses.filter(source_type='new_license_application', is_active=True, valid_up_to__gte=today)
            .exclude(source_object_id__isnull=True)
            .exclude(source_object_id='')
            .order_by('-issue_date')
            .values_list('source_object_id', flat=True)
        ):
            _append(source_object_id)

        for issued_license_id in (
            licenses.filter(is_active=True, valid_up_to__gte=today)
            .exclude(license_id__isnull=True)
            .exclude(license_id='')
            .order_by('-issue_date')
            .values_list('license_id', flat=True)
        ):
            _append(issued_license_id)

        for source_object_id in (
            licenses.filter(source_type='new_license_application')
            .exclude(source_object_id__isnull=True)
            .exclude(source_object_id='')
            .order_by('-issue_date')
            .values_list('source_object_id', flat=True)
        ):
            _append(source_object_id)

        for issued_license_id in (
            licenses.exclude(license_id__isnull=True)
            .exclude(license_id='')
            .order_by('-issue_date')
            .values_list('license_id', flat=True)
        ):
            _append(issued_license_id)

    return scoped_ids


def _should_scope_to_unit(user) -> bool:
    if _is_unscoped_admin(user):
        return False

    role_name = _normalize_role_token(getattr(getattr(user, 'role', None), 'name', ''))
    if role_name in {'licensee', 'officerincharge', 'offcierincharge', 'oic'}:
        return True
    if bool(getattr(user, 'is_oic_managed', False)):
        return True
    if _get_oic_assignment(user) is not None:
        return True

    # Non-admin users with an active mapped license should always be scoped.
    if _get_active_license_id(user):
        return True

    # Secure default: authenticated non-admin users should not see cross-license inventory.
    return True


def _get_active_license_id(user) -> str:
    scoped_ids = _collect_user_license_ids(user)
    if not scoped_ids:
        return ''

    matched_ids = set(
        BrandWarehouse.objects.filter(license_id__in=scoped_ids)
        .exclude(license_id__isnull=True)
        .exclude(license_id='')
        .values_list('license_id', flat=True)
    )
    for scoped_id in scoped_ids:
        if scoped_id in matched_ids:
            return scoped_id

    return scoped_ids[0]


def _get_active_establishment_name(user, active_license_id: str = '') -> str:
    normalized_license_id = str(active_license_id or '').strip()

    if normalized_license_id:
        try:
            from models.transactional.new_license_application.models import NewLicenseApplication
            from models.masters.license.models import License

            app = NewLicenseApplication.objects.filter(
                application_id=normalized_license_id
            ).only('establishment_name').first()
            if app and app.establishment_name:
                return str(app.establishment_name).strip()

            # If active ID is a generated License ID, resolve linked application.
            license_row = License.objects.filter(
                license_id=normalized_license_id,
                source_type='new_license_application'
            ).only('source_object_id').first()
            if license_row and license_row.source_object_id:
                app = NewLicenseApplication.objects.filter(
                    application_id=str(license_row.source_object_id).strip()
                ).only('establishment_name').first()
                if app and app.establishment_name:
                    return str(app.establishment_name).strip()
        except Exception:
            pass

    units = getattr(user, 'manufacturing_units', None)
    if units is not None:
        latest = (
            units.exclude(manufacturing_unit_name__isnull=True)
            .exclude(manufacturing_unit_name='')
            .order_by('-updated_at', '-id')
            .first()
        )
        if latest and latest.manufacturing_unit_name:
            return str(latest.manufacturing_unit_name).strip()

    return ''


def _scope_queryset_by_active_license(queryset, user, field_name: str):
    def _supports_lookup(model, lookup: str) -> bool:
        current = model
        for part in str(lookup or '').split('__'):
            if not part:
                return False
            try:
                field = current._meta.get_field(part)
            except Exception:
                return False
            if getattr(field, 'is_relation', False):
                current = getattr(field, 'related_model', None)
                if current is None:
                    return False
        return True

    scoped_ids = _collect_user_license_ids(user)
    establishment_name = _get_active_establishment_name(user)

    if scoped_ids and establishment_name:
        # Prefer strict license scoping but keep a safe fallback to establishment name.
        filters = Q(**{f'{field_name}__in': scoped_ids})
        if _supports_lookup(queryset.model, 'factory__factory_name'):
            filters |= Q(factory__factory_name__icontains=establishment_name)
        elif _supports_lookup(queryset.model, 'brand_warehouse__factory__factory_name'):
            filters |= Q(brand_warehouse__factory__factory_name__icontains=establishment_name)
        return queryset.filter(filters)

    if scoped_ids:
        return queryset.filter(**{f'{field_name}__in': scoped_ids})

    # Fallback: some deployments have license mappings that don't match stored stock rows.
    # Keep scoped users limited to their establishment name so dashboards don't show empty inventory.
    if establishment_name:
        if _supports_lookup(queryset.model, 'factory__factory_name'):
            return queryset.filter(factory__factory_name__icontains=establishment_name)
        if _supports_lookup(queryset.model, 'brand_warehouse__factory__factory_name'):
            return queryset.filter(brand_warehouse__factory__factory_name__icontains=establishment_name)
        return queryset.none()

    return queryset.none()


def _apply_license_query_filter(queryset, request, field_name: str, scoped_to_unit: bool, active_license_id: str):
    requested_license_id = str(request.query_params.get('license_id', '') or '').strip()
    if not requested_license_id:
        return queryset

    # For scoped users, never trust client license_id unless it belongs to their allowed mappings.
    if scoped_to_unit:
        scoped_ids = set(_collect_user_license_ids(request.user))
        if requested_license_id in scoped_ids:
            requested_aliases = _expand_license_aliases(requested_license_id)
            allowed_aliases = [value for value in requested_aliases if value in scoped_ids]
            if not allowed_aliases:
                return queryset.none()
            return queryset.filter(**{f'{field_name}__in': allowed_aliases})
        return queryset

    return queryset.filter(**{f'{field_name}__in': _expand_license_aliases(requested_license_id)})


def _get_scope_context(user):
    scoped_to_unit = _should_scope_to_unit(user)
    active_license_id = _get_active_license_id(user) if scoped_to_unit else ''
    return scoped_to_unit, active_license_id


def _parse_int_param(raw_value, param_name: str, default: int, min_value: int = None):
    if raw_value in (None, ''):
        return default, None

    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        return None, f'Invalid "{param_name}" value. It must be an integer.'

    if min_value is not None and value < min_value:
        return None, f'Invalid "{param_name}" value. It must be >= {min_value}.'

    return value, None


def _to_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return value != 0

    return str(value).strip().lower() in {'1', 'true', 'yes', 'y', 'on'}


class BrandWarehouseViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Brand Warehouse CRUD operations and custom actions
    Ensures ALL Sikkim brands are always shown (no brands go missing)
    """
    queryset = BrandWarehouse.objects.all().prefetch_related('utilizations', 'arrivals')
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        """Return appropriate serializer based on action"""
        if self.action == 'list':
            return BrandWarehouseSummarySerializer
        elif self.action == 'all_sikkim_brands':
            return AllSikkimBrandsSerializer
        return BrandWarehouseSerializer

    def get_queryset(self):
        """
        Return brand warehouse queryset with server-side license scoping.
        """
        queryset = BrandWarehouse.objects.all().select_related('liquor_type', 'brand', 'factory').prefetch_related('utilizations', 'arrivals')

        scoped_to_unit, active_license_id = _get_scope_context(self.request.user)

        if scoped_to_unit:
            queryset = _scope_queryset_by_active_license(queryset, self.request.user, 'license_id')

        # Apply filters from query parameters
        queryset = _apply_license_query_filter(
            queryset,
            self.request,
            field_name='license_id',
            scoped_to_unit=scoped_to_unit,
            active_license_id=active_license_id
        )

        distillery_name = self.request.query_params.get('distillery_name', None)
        if distillery_name:
            queryset = queryset.filter(factory__factory_name__icontains=distillery_name)
            
        # Backward compatible filter: `brand_type` (name) + new filter `liquor_type` (id)
        liquor_type_id = (
            self.request.query_params.get('liquor_type')
            or self.request.query_params.get('liquor_type_id')
        )
        if liquor_type_id:
            try:
                queryset = queryset.filter(liquor_type_id=int(liquor_type_id))
            except (TypeError, ValueError):
                pass

        brand_type = self.request.query_params.get('brand_type', None)
        if brand_type and not liquor_type_id:
            queryset = queryset.filter(liquor_type__liquor_type__iexact=str(brand_type).strip())
            
        status_filter = self.request.query_params.get('status', None)
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        # distinct brand_name filter for specific brand lookups
        brand_name = self.request.query_params.get('brand_name', None)
        if brand_name:
            queryset = queryset.filter(brand__brand_name__icontains=brand_name)
            
        return queryset.order_by('factory__factory_name', 'brand__brand_name', 'capacity_size__size_ml')

    def list(self, request, *args, **kwargs):
        """
        List brand warehouse entries.
        """
        try:
            queryset = self.get_queryset()
            
            # Paginate if needed
            page = self.paginate_queryset(queryset)
            if page is not None:
                serializer = self.get_serializer(page, many=True)
                return self.get_paginated_response(serializer.data)
            
            # Serialize all brands
            serializer = self.get_serializer(queryset, many=True)

            return Response(serializer.data, status=status.HTTP_200_OK)
            
        except Exception as e:
            return Response({
                'success': False,
                'error': str(e),
                'message': 'Error loading brands'
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
                'brand_id': brand_warehouse.brand_id,
                'brand_name': brand_warehouse.brand_name,
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
                'capacity_ml': int(brand_warehouse.capacity_size) if getattr(brand_warehouse, 'capacity_size_id', None) else 0,
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

    @action(detail=True, methods=['get'], url_path='canceled-permits')
    def canceled_permits(self, request, pk=None):
        """
        Get cancelled permits for a specific brand warehouse
        """
        brand_warehouse = self.get_object()
        from .serializers import BrandWarehouseTpCancellationSerializer
        
        cancellations = BrandWarehouseTpCancellation.objects.filter(
            brand_warehouse=brand_warehouse
        ).order_by('-cancellation_date')
        
        serializer = BrandWarehouseTpCancellationSerializer(cancellations, many=True)
        
        return Response({
            'success': True,
            'cancellations': serializer.data,
            'total_count': cancellations.count()
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'], url_path='tp-cancellations')
    def tp_cancellations(self, request):
        """
        Get TP cancellation rows from brand_warehouse_tp_cancellation.
        Optional query param:
          - reference_no: filter by transit permit reference number (bill no)
        """
        from .serializers import BrandWarehouseTpCancellationSerializer

        cancellations = BrandWarehouseTpCancellation.objects.all().order_by('-cancellation_date')

        reference_no = str(request.query_params.get('reference_no', '') or '').strip()
        if reference_no:
            cancellations = cancellations.filter(reference_no=reference_no)

        serializer = BrandWarehouseTpCancellationSerializer(cancellations, many=True)
        return Response({
            'success': True,
            'count': cancellations.count(),
            'results': serializer.data,
        }, status=status.HTTP_200_OK)

    @action(detail=True, methods=['get'], url_path='arrivals')
    def get_arrivals(self, request, pk=None):
        """
        Get arrival history for a brand warehouse entry
        """
        brand_warehouse = self.get_object()
        
        # Get query parameters
        limit, limit_error = _parse_int_param(
            request.query_params.get('limit'),
            param_name='limit',
            default=50,
            min_value=1
        )
        if limit_error:
            return Response({'success': False, 'error': limit_error}, status=status.HTTP_400_BAD_REQUEST)

        days, days_error = _parse_int_param(
            request.query_params.get('days'),
            param_name='days',
            default=30,
            min_value=1
        )
        if days_error:
            return Response({'success': False, 'error': days_error}, status=status.HTTP_400_BAD_REQUEST)
        
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
        
        # Get query parameters
        limit, limit_error = _parse_int_param(
            request.query_params.get('limit'),
            param_name='limit',
            default=20,
            min_value=1
        )
        if limit_error:
            return Response({'success': False, 'error': limit_error}, status=status.HTTP_400_BAD_REQUEST)

        days, days_error = _parse_int_param(
            request.query_params.get('days'),
            param_name='days',
            default=30,
            min_value=1
        )
        if days_error:
            return Response({'success': False, 'error': days_error}, status=status.HTTP_400_BAD_REQUEST)
        
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
                'brandId': brand_warehouse.brand_id,
                'brandName': brand_warehouse.brand_name,
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
        Get overall production summary for the current scoped inventory.
        """
        # Get date range
        days, days_error = _parse_int_param(
            request.query_params.get('days'),
            param_name='days',
            default=30,
            min_value=1
        )
        if days_error:
            return Response({'success': False, 'error': days_error}, status=status.HTTP_400_BAD_REQUEST)
        start_date = timezone.now().date() - timedelta(days=days)
        
        # Build warehouse scope dynamically by active license mapping.
        scoped_to_unit, active_license_id = _get_scope_context(request.user)
        warehouse_queryset = BrandWarehouse.objects.all()
        if scoped_to_unit:
            warehouse_queryset = _scope_queryset_by_active_license(
                warehouse_queryset,
                request.user,
                'license_id'
            )

        warehouse_queryset = _apply_license_query_filter(
            warehouse_queryset,
            request,
            field_name='license_id',
            scoped_to_unit=scoped_to_unit,
            active_license_id=active_license_id
        )
        
        # Get production data
        production_data = ProductionBatch.objects.filter(
            brand_warehouse__in=warehouse_queryset,
            production_date__gte=start_date
        ).aggregate(
            total_batches=Count('id'),
            total_quantity=Sum('quantity_produced'),
            avg_batch_size=Avg('quantity_produced')
        )
        
        # Get today's production
        today_production = ProductionBatch.objects.filter(
            brand_warehouse__in=warehouse_queryset,
            production_date=timezone.now().date()
        ).aggregate(
            today_quantity=Sum('quantity_produced'),
            today_batches=Count('id')
        )
        
        # Get this week's production
        week_start = timezone.now().date() - timedelta(days=timezone.now().weekday())
        week_production = ProductionBatch.objects.filter(
            brand_warehouse__in=warehouse_queryset,
            production_date__gte=week_start
        ).aggregate(
            week_quantity=Sum('quantity_produced'),
            week_batches=Count('id')
        )
        
        # Get this month's production
        month_start = timezone.now().date().replace(day=1)
        month_production = ProductionBatch.objects.filter(
            brand_warehouse__in=warehouse_queryset,
            production_date__gte=month_start
        ).aggregate(
            month_quantity=Sum('quantity_produced'),
            month_batches=Count('id')
        )
        
        # Get last production date
        last_production = ProductionBatch.objects.filter(
            brand_warehouse__in=warehouse_queryset
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
        Initialize/refresh stock inventory context.
        Scoped users are constrained to their active mapped license_id.
        """
        try:
            if _should_scope_to_unit(request.user):
                active_license_id = _get_active_license_id(request.user)
                if not active_license_id:
                    return Response({
                        'success': False,
                        'message': 'No active license mapping found for this user.'
                    }, status=status.HTTP_400_BAD_REQUEST)

                all_brands = BrandWarehouse.objects.filter(
                    license_id=active_license_id
                ).prefetch_related('arrivals', 'utilizations')

                return Response({
                    'success': True,
                    'message': f'Loaded {all_brands.count()} brands for license {active_license_id}',
                    'total_brands': all_brands.count(),
                    'license_id': active_license_id
                }, status=status.HTTP_200_OK)

            # Non-scoped/admin fallback retains existing global behavior.
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
            days, days_error = _parse_int_param(
                request.data.get('days'),
                param_name='days',
                default=30,
                min_value=1
            )
            if days_error:
                return Response({'success': False, 'error': days_error}, status=status.HTTP_400_BAD_REQUEST)
            
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
        confirm_delete = request.data.get('confirm_delete')
        if confirm_delete is None:
            confirm_delete = request.query_params.get('confirm_delete')

        if not _to_bool(confirm_delete):
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
                'message': f'Brand warehouse "{instance.brand_name}" has been soft deleted',
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
                'message': f'Brand warehouse "{instance.brand_name}" has been restored',
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
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Filter queryset based on query parameters"""
        queryset = BrandWarehouseUtilization.objects.all().select_related('brand_warehouse')

        scoped_to_unit, active_license_id = _get_scope_context(self.request.user)
        if scoped_to_unit:
            queryset = _scope_queryset_by_active_license(
                queryset,
                self.request.user,
                'brand_warehouse__license_id'
            )

        queryset = _apply_license_query_filter(
            queryset,
            self.request,
            field_name='license_id',
            scoped_to_unit=scoped_to_unit,
            active_license_id=active_license_id
        )

        # Backward compatibility for older rows where utilization.license_id may be null.
        if scoped_to_unit:
            scoped_ids = _collect_user_license_ids(self.request.user)
            queryset = queryset.filter(
                Q(license_id__in=scoped_ids) |
                (Q(license_id__isnull=True) & Q(brand_warehouse__license_id__in=scoped_ids)) |
                (Q(license_id='') & Q(brand_warehouse__license_id__in=scoped_ids))
            )
        
        # Filter by brand warehouse
        brand_warehouse_id = self.request.query_params.get('brand_warehouse', None)
        if brand_warehouse_id:
            queryset = queryset.filter(brand_warehouse_id=brand_warehouse_id)
            
        # Filter by status
        status_filter = self.request.query_params.get('status', None)
        if status_filter:
            queryset = queryset.filter(status=status_filter)
            
        # Newest first: date desc, then id desc for same-day rows.
        return queryset.order_by('-date', '-id')


class ProductionBatchViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Production Batch CRUD operations
    """
    serializer_class = ProductionBatchSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = ProductionBatch.objects.all().select_related('brand_warehouse')
        if _should_scope_to_unit(self.request.user):
            queryset = _scope_queryset_by_active_license(
                queryset,
                self.request.user,
                'brand_warehouse__license_id'
            )
        return queryset

    def get_serializer_class(self):
        """Return appropriate serializer based on action"""
        if self.action == 'create':
            return CreateProductionBatchSerializer
        return ProductionBatchSerializer

    def filter_queryset(self, queryset):
        """Filter queryset based on query parameters"""
        scoped_to_unit, active_license_id = _get_scope_context(self.request.user)
        queryset = _apply_license_query_filter(
            queryset,
            self.request,
            field_name='brand_warehouse__license_id',
            scoped_to_unit=scoped_to_unit,
            active_license_id=active_license_id
        )

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
        if _should_scope_to_unit(request.user):
            daily_batches = _scope_queryset_by_active_license(
                daily_batches,
                request.user,
                'brand_warehouse__license_id'
            )
        
        # Calculate summary
        summary_data = daily_batches.aggregate(
            total_quantity=Sum('quantity_produced'),
            batch_count=Count('id')
        )
        
        # Get unique brands and managers
        brands_produced = list(daily_batches.values_list(
            'brand_warehouse__brand__brand_name', flat=True
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

        if _should_scope_to_unit(request.user):
            allowed = _scope_queryset_by_active_license(
                BrandWarehouse.objects.filter(id=brand_warehouse.id),
                request.user,
                'license_id'
            ).exists()
            if not allowed:
                return Response({
                    'success': False,
                    'error': 'You are not allowed to access this brand warehouse.'
                }, status=status.HTTP_403_FORBIDDEN)
        
        # Get date range
        days, days_error = _parse_int_param(
            request.query_params.get('days'),
            param_name='days',
            default=30,
            min_value=1
        )
        if days_error:
            return Response({'success': False, 'error': days_error}, status=status.HTTP_400_BAD_REQUEST)
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
                'brandId': brand_warehouse.brand_id,
                'brandName': brand_warehouse.brand_name,
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
