from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from models.transactional.supply_chain.brand_warehouse.models import BrandWarehouse
from .models import UserManufacturingUnit

class ManufacturingUnitListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        try:
            rows = BrandWarehouse.objects.exclude(
                factory__isnull=True
            ).exclude(
                factory__factory_name__isnull=True
            ).exclude(
                factory__factory_name=''
            ).exclude(
                license_id__isnull=True
            ).exclude(
                license_id=''
            ).values('factory__factory_name', 'license_id', 'liquor_type__liquor_type')

            grouped = {}
            for row in rows:
                name = str(row.get('factory__factory_name') or '').strip()
                if not name:
                    continue
                grouped.setdefault(name, []).append(row)

            data = []
            for name, unit_rows in grouped.items():
                # Use approved license ids only (NA/...).
                selected_license_id = ''
                l_type_raw = ''
                for row in unit_rows:
                    candidate = str(row.get('license_id') or '').strip()
                    if not l_type_raw:
                        l_type_raw = str(row.get('liquor_type__liquor_type') or '')
                    if not candidate:
                        continue
                    if candidate.startswith('NA/'):
                        selected_license_id = candidate
                        break

                if not selected_license_id:
                    continue

                l_type = 'Brewery' if 'beer' in l_type_raw.lower() else 'Distillery'

                data.append({
                    'name': name,
                    'licensee_id': selected_license_id,
                    'type': l_type
                })
            
            return Response({'success': True, 'data': data})
        except Exception as e:
            return Response({'success': False, 'error': str(e)}, status=500)

class UserUnitsAPIView(APIView):
    def get(self, request):
        units = UserManufacturingUnit.objects.filter(user=request.user)
        data = [{
            'manufacturing_unit_name': u.manufacturing_unit_name,
            'licensee_id': u.licensee_id,
            'license_type': u.license_type
        } for u in units]
        return Response({'success': True, 'data': data})
