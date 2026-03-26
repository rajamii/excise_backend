from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.db.models import Q, Max, Count
import logging
from models.transactional.supply_chain.brand_warehouse.models import BrandWarehouse
from .models import MasterLiquorType, MasterLiquorCategory, MasterBottleType, MasterBrandList
from .serializers import (
    MasterLiquorTypeSerializer,
    MasterLiquorCategorySerializer,
    MasterBottleTypeSerializer,
    MasterBrandListSerializer,
)

logger = logging.getLogger(__name__)


class MasterLiquorTypeListView(APIView):
    """
    Master table endpoint for liquor types.

    Query params:
    - include_brands=true|false (default false)
    - distillery=<partial name> (optional)
    """

    def get(self, request):
        include_brands = str(request.query_params.get('include_brands') or '').strip().lower() in {'1', 'true', 'yes'}
        distillery_filter = str(request.query_params.get('distillery') or '').strip()

        qs = MasterLiquorType.objects.all()

        data = MasterLiquorTypeSerializer(qs, many=True).data

        if not include_brands:
            return Response({'success': True, 'data': data, 'total': len(data)})

        brand_qs = BrandWarehouse.objects.all()
        if distillery_filter:
            brand_qs = brand_qs.filter(distillery_name__icontains=distillery_filter)

        brand_rows = (
            brand_qs.exclude(brand__isnull=True)
            .values('liquor_type')
            .annotate(brand_count=Count('id'))
        )
        count_map = {row['liquor_type']: int(row.get('brand_count') or 0) for row in brand_rows}

        for row in data:
            liquor_type_id = row.get('id')
            row['brand_count'] = count_map.get(liquor_type_id, 0)

        return Response({'success': True, 'data': data, 'total': len(data)})


class BrandSizeListView(APIView):
    def get(self, request):
        try:
            # Get distillery filter from query params (defaults to Sikkim Distilleries Ltd)
            distillery_filter = request.GET.get('distillery', 'Sikkim Distilleries Ltd')

            rows = BrandWarehouse.objects.filter(
                distillery_name__icontains=distillery_filter
            ).exclude(
                brand__isnull=True
            ).exclude(
                capacity_size__isnull=True
            ).values(
                'brand_id', 'brand__brand_name', 'capacity_size__size_ml'
            )

            grouped: dict[int, dict] = {}
            for row in rows:
                brand_id = row.get('brand_id')
                brand_name = str(row.get('brand__brand_name') or '').strip()
                size = row.get('capacity_size__size_ml')
                if not brand_id or not brand_name or size is None:
                    continue
                grouped.setdefault(int(brand_id), {'brandName': brand_name, 'sizes': set()})['sizes'].add(int(size))

            result = []
            for brand_id, payload in grouped.items():
                result.append({
                    'brandId': int(brand_id),
                    'brandName': payload['brandName'],
                    'sizes': sorted(list(payload['sizes'])),
                    'manufacturingUnit': distillery_filter
                })

            # Sort by brand name
            result.sort(key=lambda x: x['brandName'])
            
            logger.info(f"BrandSizeListView: Returning {len(result)} brands for distillery: {distillery_filter}")
            
            return Response({
                'success': True,
                'data': result,
                'distillery': distillery_filter,
                'total_brands': len(result)
            })
            
        except Exception as e:
            logger.error(f"Error in BrandSizeListView: {str(e)}", exc_info=True)
            return Response({
                'success': False,
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class LiquorRatesView(APIView):
    def get(self, request):
        try:
            brand_name = request.query_params.get('brand_name')
            pack_size_ml = request.query_params.get('pack_size_ml')

            logger.debug("LiquorRatesView request: brand_name=%r pack_size_ml=%r", brand_name, pack_size_ml)

            if not brand_name or not pack_size_ml:
                return Response({
                    'success': False,
                    'error': 'Both brand_name and pack_size_ml are required parameters'
                }, status=status.HTTP_400_BAD_REQUEST)

            
            try:
                pack_size_ml = int(pack_size_ml)
            except ValueError:
                return Response({
                    'success': False,
                    'error': 'pack_size_ml must be a valid number'
                }, status=status.HTTP_400_BAD_REQUEST)

            normalized_brand = brand_name.strip()
            base_qs = BrandWarehouse.objects.filter(capacity_size__size_ml=pack_size_ml)

            # Prefer exact match first, then fall back to contains for legacy name variations.
            warehouse_row = base_qs.filter(brand__brand_name__iexact=normalized_brand).first()
            if not warehouse_row:
                warehouse_row = base_qs.filter(
                    Q(brand__brand_name__icontains=normalized_brand) |
                    Q(brand__brand_name__istartswith=normalized_brand)
                ).first()

            logger.debug("LiquorRatesView warehouse query result: %s", warehouse_row)

            if not warehouse_row:
                return Response({
                    'success': False,
                    'error': f'No data found for brand: {brand_name} and size: {pack_size_ml}ml'
                }, status=status.HTTP_404_NOT_FOUND)

            response_data = {
                'brandId': warehouse_row.brand_id,
                'brand': warehouse_row.brand_name,
                'size': f"{warehouse_row.capacity_size}ml",
                'educationCess': float(warehouse_row.education_cess_rs_per_case or 0),
                'exciseDuty': float(warehouse_row.excise_duty_rs_per_case or 0),
                'additionalExcise': float(warehouse_row.additional_excise_duty_rs_per_case or 0),
                
                # New fields
                'brandOwner': '',
                'liquorType': warehouse_row.brand_type,
                'exFactoryPrice': float(warehouse_row.ex_factory_price_rs_per_case or 0),
                'manufacturingUnitName': warehouse_row.distillery_name,

                'additionalExcise12_5': float(warehouse_row.additional_excise_duty_12_5_percent_rs_per_case or 0),
                'bottlingFee': 0,
                'exportFee': 0,
                'mrpPerBottle': float(warehouse_row.mrp_rs_per_bottle or 0),
                'totalPricePerCase': 0
            }

            logger.debug("LiquorRatesView response payload built for brand=%r size_ml=%s", brand_name, pack_size_ml)

            return Response({
                'success': True,
                'data': response_data
            })

        except Exception as e:
            logger.exception("Error in LiquorRatesView")
            return Response({
                'success': False,
                'error': f'Internal server error: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class MasterLiquorCategoryListView(APIView):
    """
    Master table endpoint for pack sizes (ml).

    Query params:
    - include_zero=true|false (default false)
    """

    def get(self, request):
        include_zero = str(request.query_params.get('include_zero') or '').strip().lower() in {'1', 'true', 'yes'}

        qs = MasterLiquorCategory.objects.all()
        if not include_zero:
            qs = qs.filter(size_ml__gt=0)

        data = MasterLiquorCategorySerializer(qs, many=True).data
        return Response({'success': True, 'data': data, 'total': len(data)})


class MasterBottleTypeListCreateView(APIView):
    """
    Master table endpoint for bottle types (used by transit permits).

    GET: list bottle types (optionally active-only)
      - active_only=true|false (default true)

    POST: create bottle type
    """

    def get(self, request):
        active_only = str(request.query_params.get('active_only') or '').strip().lower() not in {'0', 'false', 'no'}

        qs = MasterBottleType.objects.all()
        if active_only:
            qs = qs.filter(is_active=True)

        data = MasterBottleTypeSerializer(qs.order_by('bottle_type'), many=True).data
        return Response({'success': True, 'data': data, 'total': len(data)})

    def post(self, request):
        serializer = MasterBottleTypeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        obj = serializer.save()
        return Response({'success': True, 'data': MasterBottleTypeSerializer(obj).data}, status=status.HTTP_201_CREATED)


class MasterBottleTypeDetailView(APIView):
    """
    Detail endpoint for bottle types.

    GET/PATCH/DELETE by id.
    """

    def get_object(self, pk: int):
        try:
            return MasterBottleType.objects.get(pk=pk)
        except MasterBottleType.DoesNotExist:
            return None

    def get(self, request, pk: int):
        obj = self.get_object(pk)
        if not obj:
            return Response({'success': False, 'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)
        return Response({'success': True, 'data': MasterBottleTypeSerializer(obj).data})

    def patch(self, request, pk: int):
        obj = self.get_object(pk)
        if not obj:
            return Response({'success': False, 'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)
        serializer = MasterBottleTypeSerializer(obj, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({'success': True, 'data': serializer.data})

    def delete(self, request, pk: int):
        obj = self.get_object(pk)
        if not obj:
            return Response({'success': False, 'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)
        obj.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class MasterBrandListListCreateView(APIView):
    """
    Master table endpoint for brands.

    GET: list master brands (optionally filtered by ?q=)
    POST: create a new master brand
    """

    def get(self, request):
        qs = MasterBrandList.objects.all()
        q = str(request.query_params.get('q') or '').strip()
        if q:
            qs = qs.filter(brand_name__icontains=q)
        data = MasterBrandListSerializer(qs.order_by('brand_name'), many=True).data
        return Response({'success': True, 'data': data, 'total': len(data)})

    def post(self, request):
        serializer = MasterBrandListSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        obj = serializer.save()
        return Response({'success': True, 'data': MasterBrandListSerializer(obj).data}, status=status.HTTP_201_CREATED)

class GetUserEntitiesView(APIView):
    def get(self, request):
        try:
            licensee_id = request.query_params.get('licensee_id')
            
            # If no licensee_id provided, default to '01202506012' for testing/demo if needed
            # But the requirement is to use the logged in user's ID
            if not licensee_id:
                # Optional: Retrieve from User/Session if not in params
                # For now error out
                return Response({
                    'success': False,
                    'error': 'licensee_id is required'
                }, status=status.HTTP_400_BAD_REQUEST)

            rows = BrandWarehouse.objects.filter(
                license_id=licensee_id
            ).exclude(
                distillery_name__isnull=True
            ).exclude(
                distillery_name=''
            ).values(
                'distillery_name'
            ).annotate(
                sample_type=Max('liquor_type__liquor_type')
            )

            entities = []
            for row in rows:
                unit_name = row.get('distillery_name')
                l_type = row.get('sample_type') or ""
                
                entity_type = 'Brewery' if 'beer' in l_type.lower() else 'Distillery'
                
                entities.append({
                    'name': unit_name,
                    'licenseId': licensee_id,
                    'type': entity_type
                })
            
            return Response({
                'success': True,
                'data': entities
            })
            
        except Exception as e:
            logger.error(f"Error in GetUserEntitiesView: {str(e)}", exc_info=True)
            return Response({
                'success': False,
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
