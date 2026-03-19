from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.db.models import Q, Max
import logging
from models.transactional.supply_chain.brand_warehouse.models import BrandWarehouse
from models.masters.supply_chain.transit_permit.models import TransitPermitBottleType
from models.transactional.supply_chain.ena_transit_permit_details.models import EnaTransitPermitDetail
from .serializers import ApprovedBrandDetailsSerializer, BottleTypeSerializer

logger = logging.getLogger(__name__)

class BrandSizeListView(APIView):
    def get(self, request):
        try:
            # Get distillery filter from query params (defaults to Sikkim Distilleries Ltd)
            distillery_filter = request.GET.get('distillery', 'Sikkim Distilleries Ltd')

            rows = BrandWarehouse.objects.filter(
                distillery_name__icontains=distillery_filter
            ).exclude(
                brand_details__isnull=True
            ).exclude(
                brand_details=''
            ).exclude(
                capacity_size__isnull=True
            ).values(
                'brand_details', 'capacity_size'
            )

            grouped: dict[str, set[int]] = {}
            for row in rows:
                brand_name = str(row.get('brand_details') or '').strip()
                size = row.get('capacity_size')
                if not brand_name or size is None:
                    continue
                grouped.setdefault(brand_name, set()).add(int(size))

            result = []
            for brand_name, sizes_set in grouped.items():
                result.append({
                    'brandName': brand_name,
                    'sizes': sorted(list(sizes_set)),
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

            print(f"DEBUG: Received request - Brand: '{brand_name}', Size: '{pack_size_ml}'")

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
            base_qs = BrandWarehouse.objects.filter(capacity_size=pack_size_ml)

            # Prefer exact match first, then fall back to contains for legacy name variations.
            warehouse_row = base_qs.filter(brand_details__iexact=normalized_brand).first()
            if not warehouse_row:
                warehouse_row = base_qs.filter(
                    Q(brand_details__icontains=normalized_brand) |
                    Q(brand_details__istartswith=normalized_brand)
                ).first()

            print(f"DEBUG: Database query result: {warehouse_row}")

            if not warehouse_row:
                return Response({
                    'success': False,
                    'error': f'No data found for brand: {brand_name} and size: {pack_size_ml}ml'
                }, status=status.HTTP_404_NOT_FOUND)

            response_data = {
                'brand': warehouse_row.brand_details,
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

            print(f"DEBUG: Successfully returning: {response_data}")

            return Response({
                'success': True,
                'data': response_data
            })

        except Exception as e:
            print(f"DEBUG: Error occurred: {str(e)}")
            import traceback
            print(f"DEBUG: Traceback: {traceback.format_exc()}")
            return Response({
                'success': False,
                'error': f'Internal server error: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

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
                sample_type=Max('brand_type')
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

class ApprovedBrandDetailsView(APIView):
    """
    Read-only API to fetch brand details for approved licensees only.
    1. Validates license exists and is_approved=True in NewLicenseApplication
    2. Gets distillery/manufacturing unit names from transit_permit_details for that licensee
    3. Fetches ALL brands from brand_warehouse matching those distillery names
    4. Attaches bottle_type from approved transit permits dynamically
    """
    def get(self, request):
        try:
            license_id = request.query_params.get('license_id')

            if not license_id:
                return Response({
                    'success': False,
                    'error': 'license_id is required'
                }, status=status.HTTP_400_BAD_REQUEST)

            # Step 1: Check license exists and is active in the licenses table
            from models.masters.license.models import License
            is_approved = License.objects.filter(
                license_id=license_id,
                is_active=True
            ).exists()

            if not is_approved:
                return Response({
                    'success': False,
                    'error': 'License is not approved or does not exist'
                }, status=status.HTTP_403_FORBIDDEN)

            # Step 2: Get approved workflow stage name dynamically
            from auth.workflow.models import WorkflowStage
            from auth.workflow.constants import WORKFLOW_IDS
            approved_stage = WorkflowStage.objects.filter(
                workflow_id=WORKFLOW_IDS['TRANSIT_PERMIT'],
                is_final=True,
                name__icontains='Approved'
            ).values_list('name', flat=True).first()

            # Step 3: Get distillery names from transit_permit_details for this licensee
            # (approved permits tell us which manufacturing units supply this licensee)
            distillery_names = list(
                EnaTransitPermitDetail.objects.filter(
                    licensee_id=license_id,
                    status=approved_stage
                ).exclude(
                    manufacturing_unit_name=''
                ).exclude(
                    manufacturing_unit_name__isnull=True
                ).values_list('manufacturing_unit_name', flat=True).distinct()
            )

            if not distillery_names:
                return Response({
                    'success': True,
                    'data': [],
                    'total': 0,
                    'licenseId': license_id,
                    'message': 'No approved transit permits found for this license'
                })

            # Step 4: Fetch ALL brands from brand_warehouse for those distillery names
            warehouse_brands = BrandWarehouse.objects.filter(
                distillery_name__in=distillery_names
            ).exclude(
                brand_details__isnull=True
            ).exclude(
                brand_details=''
            ).exclude(
                brand_type__isnull=True
            ).exclude(
                brand_type=''
            ).exclude(
                capacity_size__isnull=True
            ).values(
                'brand_details',
                'brand_type',
                'capacity_size',
                'distillery_name'
            ).distinct().order_by('brand_details', 'capacity_size')

            # Step 5: Build bottle_type map from approved transit permits
            transit_bottle_map = {}
            transit_permits = EnaTransitPermitDetail.objects.filter(
                licensee_id=license_id,
                manufacturing_unit_name__in=distillery_names,
                status=approved_stage
            ).exclude(
                bottle_type=''
            ).exclude(
                bottle_type__isnull=True
            ).values('brand', 'size_ml', 'bottle_type')

            for permit in transit_permits:
                key = (permit['brand'].strip().lower(), permit['size_ml'])
                transit_bottle_map[key] = permit['bottle_type']

            # Step 6: Build response
            brand_data = []
            for brand in warehouse_brands:
                key = (brand['brand_details'].strip().lower(), brand['capacity_size'])
                brand_data.append({
                    'brandName': brand['brand_details'],
                    'liquorType': brand['brand_type'],
                    'bottleSize': brand['capacity_size'],
                    'bottleType': transit_bottle_map.get(key, None),
                    'manufacturingUnit': brand['distillery_name']
                })

            logger.info(f"ApprovedBrandDetailsView: {len(brand_data)} brands for license_id={license_id}, distilleries={distillery_names}")

            return Response({
                'success': True,
                'data': brand_data,
                'total': len(brand_data),
                'licenseId': license_id
            })

        except Exception as e:
            logger.error(f"Error in ApprovedBrandDetailsView: {str(e)}", exc_info=True)
            return Response({
                'success': False,
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
