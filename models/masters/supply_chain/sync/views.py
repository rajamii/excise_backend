from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
import logging

from models.masters.supply_chain.ena_distillery_details.models import enaDistilleryTypes
from models.transactional.supply_chain.brand_warehouse.models import BrandWarehouse
from models.masters.supply_chain.transit_permit.models import TransitPermitBottleType, BrandMlInCases
from .models import SyncRecord

logger = logging.getLogger(__name__)


def get_sync_status(entity_type, entity_id):
    """Returns is_sync value for a given entity. Defaults to 0 if not tracked yet."""
    try:
        return SyncRecord.objects.get(entity_type=entity_type, entity_id=entity_id).is_sync
    except SyncRecord.DoesNotExist:
        return 0


def parse_is_sync_filter(request):
    """Returns None (no filter), 0, or 1 based on ?is_sync= query param."""
    val = request.query_params.get('is_sync')
    if val in ('0', '1'):
        return int(val)
    return None


class FactoryListView(APIView):
    """GET /masters/supply_chain/sync/factory-list/"""

    def get(self, request):
        try:
            is_sync_filter = parse_is_sync_filter(request)
            factories = enaDistilleryTypes.objects.all().order_by('id')

            result = []
            for f in factories:
                sync_val = get_sync_status('factory', f.id)
                if is_sync_filter is not None and sync_val != is_sync_filter:
                    continue
                result.append({
                    'factory_id': f.id,
                    'factory_name': f.distillery_name,
                    'licensee_id': f.licensee_id or '',
                    'factory_address': f.distillery_address,
                    'factory_state': f.distillery_state,
                    'is_sync': sync_val,
                })

            return Response({'factory_list': result})

        except Exception as e:
            logger.error(f"FactoryListView error: {e}", exc_info=True)
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class LiquorTypeListView(APIView):
    """GET /masters/supply_chain/sync/liquor-type-list/"""

    def get(self, request):
        try:
            is_sync_filter = parse_is_sync_filter(request)

            # Get distinct liquor types from brand_warehouse
            rows = BrandWarehouse.objects.exclude(
                brand_type__isnull=True
            ).exclude(
                brand_type=''
            ).values('brand_type', 'distillery_name').distinct().order_by('brand_type')

            result = []
            for idx, row in enumerate(rows, start=1):
                sync_val = get_sync_status('liquor_type', idx)
                if is_sync_filter is not None and sync_val != is_sync_filter:
                    continue
                result.append({
                    'liquor_type_id': idx,
                    'liquor_type_name': row['brand_type'],
                    'is_sync': sync_val,
                })

            return Response({'liquor_type_list': result})

        except Exception as e:
            logger.error(f"LiquorTypeListView error: {e}", exc_info=True)
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class BrandListView(APIView):
    """GET /masters/supply_chain/sync/brand-list/"""

    def get(self, request):
        try:
            is_sync_filter = parse_is_sync_filter(request)

            brands = BrandWarehouse.objects.exclude(
                brand_details__isnull=True
            ).exclude(
                brand_details=''
            ).order_by('id')

            factory_map = {
                f.distillery_name: f.id
                for f in enaDistilleryTypes.objects.all()
            }

            # Build liquor_type index from distinct (brand_type, distillery_name)
            lt_rows = list(
                BrandWarehouse.objects.exclude(brand_type__isnull=True).exclude(brand_type='')
                .values('brand_type', 'distillery_name').distinct().order_by('brand_type')
            )
            lt_id_map = {
                (r['brand_type'], r['distillery_name']): idx
                for idx, r in enumerate(lt_rows, start=1)
            }

            result = []
            for b in brands:
                sync_val = get_sync_status('brand', b.id)
                if is_sync_filter is not None and sync_val != is_sync_filter:
                    continue
                result.append({
                    'brand_id': b.id,
                    'brand_name': b.brand_details,
                    'brand_owner': b.distillery_name,
                    'liquor_type_id': lt_id_map.get((b.brand_type, b.distillery_name)),
                    'factory_id': factory_map.get(b.distillery_name),
                    'is_sync': sync_val,
                })

            return Response({'brand_list': result})

        except Exception as e:
            logger.error(f"BrandListView error: {e}", exc_info=True)
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class BottleTypeListView(APIView):
    """GET /masters/supply_chain/sync/bottle-type-list/"""

    def get(self, request):
        try:
            is_sync_filter = parse_is_sync_filter(request)
            bottle_types = TransitPermitBottleType.objects.filter(is_active=True).order_by('id')

            result = []
            for bt in bottle_types:
                sync_val = get_sync_status('bottle_type', bt.id)
                if is_sync_filter is not None and sync_val != is_sync_filter:
                    continue
                result.append({
                    'bottle_type_id': bt.id,
                    'bottle_type_name': bt.bottle_type,
                    'is_sync': sync_val,
                })

            return Response({'bottle_type_list': result})

        except Exception as e:
            logger.error(f"BottleTypeListView error: {e}", exc_info=True)
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class BottleSizeListView(APIView):
    """GET /masters/supply_chain/sync/bottle-size-list/"""

    def get(self, request):
        try:
            is_sync_filter = parse_is_sync_filter(request)
            sizes = BrandMlInCases.objects.all().order_by('ml')

            result = []
            for s in sizes:
                sync_val = get_sync_status('bottle_size', s.id)
                if is_sync_filter is not None and sync_val != is_sync_filter:
                    continue
                result.append({
                    'bottle_size_id': s.id,
                    'size_ml': s.ml,
                    'pieces_per_case': s.pieces_in_case,
                    'is_sync': sync_val,
                })

            return Response({'bottle_size_list': result})

        except Exception as e:
            logger.error(f"BottleSizeListView error: {e}", exc_info=True)
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class UpdateSyncStatusView(APIView):
    """
    POST /masters/supply_chain/sync/update-sync-status/
    Called by LMSDB after successfully syncing records.
    Payload: [{"entity_type": "factory", "id": 1, "is_sync": 1}, ...]
    """

    def post(self, request):
        try:
            payload = request.data
            if not isinstance(payload, list):
                return Response(
                    {'error': 'Payload must be a list of {entity_type, id, is_sync}'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            updated = []
            errors = []
            for item in payload:
                entity_type = item.get('entity_type')
                entity_id = item.get('id')
                is_sync = item.get('is_sync')

                if entity_type not in ('factory', 'liquor_type', 'brand', 'bottle_type', 'bottle_size'):
                    errors.append({'id': entity_id, 'error': f'Unknown entity_type: {entity_type}'})
                    continue

                if is_sync not in (0, 1):
                    errors.append({'id': entity_id, 'error': 'is_sync must be 0 or 1'})
                    continue

                record, _ = SyncRecord.objects.update_or_create(
                    entity_type=entity_type,
                    entity_id=entity_id,
                    defaults={'is_sync': is_sync}
                )
                updated.append({'entity_type': entity_type, 'id': entity_id, 'is_sync': is_sync})

            return Response({
                'success': True,
                'updated': len(updated),
                'errors': errors
            })

        except Exception as e:
            logger.error(f"UpdateSyncStatusView error: {e}", exc_info=True)
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
