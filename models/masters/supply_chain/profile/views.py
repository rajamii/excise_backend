from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from .models import SupplyChainUserProfile
from .serializers import SupplyChainUserProfileSerializer
from models.transactional.supply_chain.brand_warehouse.models import BrandWarehouse
from models.masters.license.models import License


def _resolve_approved_license_id(user, raw_license_id: str = '', unit_name: str = '') -> str:
    requested = str(raw_license_id or '').strip()
    if requested.startswith('NA/'):
        return requested

    user_licenses = License.objects.filter(
        applicant=user,
        source_type='new_license_application',
        is_active=True
    ).order_by('-issue_date')

    if requested:
        by_source = user_licenses.filter(source_object_id=requested).first()
        if by_source and by_source.license_id:
            return str(by_source.license_id).strip()

        by_license = user_licenses.filter(license_id=requested).first()
        if by_license and by_license.license_id:
            return str(by_license.license_id).strip()

    normalized_unit_name = str(unit_name or '').strip()
    if normalized_unit_name:
        try:
            from models.transactional.new_license_application.models import NewLicenseApplication

            latest_app = NewLicenseApplication.objects.filter(
                applicant=user,
                establishment_name__iexact=normalized_unit_name
            ).order_by('-created_at').first()
            if latest_app:
                lic = user_licenses.filter(source_object_id=str(latest_app.application_id)).first()
                if lic and lic.license_id:
                    return str(lic.license_id).strip()
        except Exception:
            pass

    latest = user_licenses.first()
    if latest and latest.license_id:
        return str(latest.license_id).strip()

    return ''

class ManufacturingUnitListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        try:
            rows = BrandWarehouse.objects.exclude(
                distillery_name__isnull=True
            ).exclude(
                distillery_name=''
            ).exclude(
                license_id__isnull=True
            ).exclude(
                license_id=''
            ).values('distillery_name', 'license_id', 'brand_type')

            grouped = {}
            for row in rows:
                name = str(row.get('distillery_name') or '').strip()
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
                        l_type_raw = str(row.get('brand_type') or '')
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

class SupplyChainUserProfileView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        try:
            profile = SupplyChainUserProfile.objects.get(user=request.user)
            serializer = SupplyChainUserProfileSerializer(profile)
            return Response({'success': True, 'exists': True, 'data': serializer.data})
        except SupplyChainUserProfile.DoesNotExist:
            return Response({'success': True, 'exists': False, 'data': None})

    def post(self, request):
        if SupplyChainUserProfile.objects.filter(user=request.user).exists():
             return Response({'success': False, 'error': 'Profile already exists'}, status=400)

        serializer = SupplyChainUserProfileSerializer(data=request.data)
        if serializer.is_valid():
            # 1. Save/Create in Permanent History (UserManufacturingUnit)
            from .models import UserManufacturingUnit
            unit_data = serializer.validated_data
            approved_license_id = _resolve_approved_license_id(
                user=request.user,
                raw_license_id=str(unit_data.get('licensee_id') or ''),
                unit_name=str(unit_data.get('manufacturing_unit_name') or '')
            )
            if not approved_license_id.startswith('NA/'):
                return Response(
                    {'success': False, 'error': 'Approved license not found. Please use approved NA license.'},
                    status=400
                )
            
            UserManufacturingUnit.objects.update_or_create(
                user=request.user, 
                licensee_id=approved_license_id,
                defaults={
                    'manufacturing_unit_name': unit_data['manufacturing_unit_name'],
                    'license_type': unit_data.get('license_type'),
                    'address': unit_data.get('address')
                }
            )

            # 2. Set as Active Profile (SupplyChainUserProfile)
            # If profile exists, update it. If not, create it.
            profile, created = SupplyChainUserProfile.objects.update_or_create(
                user=request.user,
                defaults={
                    'manufacturing_unit_name': unit_data['manufacturing_unit_name'],
                    'licensee_id': approved_license_id,
                    'license_type': unit_data.get('license_type'),
                    'address': unit_data.get('address')
                }
            )
            
            return Response({'success': True, 'data': serializer.data})
        return Response({'success': False, 'error': serializer.errors}, status=400)

    def delete(self, request):
        try:
            profile = SupplyChainUserProfile.objects.get(user=request.user)
            # We only delete the ACTIVE session, not the history
            profile.delete()
            return Response({'success': True, 'message': 'Active profile cleared'})
        except SupplyChainUserProfile.DoesNotExist:
            return Response({'success': False, 'error': 'Profile not found'}, status=404)

class UserUnitsAPIView(APIView):
    def get(self, request):
        from .models import UserManufacturingUnit
        units = UserManufacturingUnit.objects.filter(user=request.user)
        data = [{
            'manufacturing_unit_name': u.manufacturing_unit_name,
            'licensee_id': u.licensee_id,
            'license_type': u.license_type
        } for u in units]
        return Response({'success': True, 'data': data})

class SwitchUnitAPIView(APIView):
    def post(self, request):
        licensee_id = request.data.get('licensee_id')
        if not licensee_id:
            return Response({'success': False, 'error': 'Licensee ID required'}, status=400)
            
        from .models import UserManufacturingUnit, SupplyChainUserProfile
        try:
            approved_license_id = _resolve_approved_license_id(
                user=request.user,
                raw_license_id=str(licensee_id or '')
            )

            # Find the unit in history
            target_unit = (
                UserManufacturingUnit.objects.filter(user=request.user, licensee_id=approved_license_id).first()
                or UserManufacturingUnit.objects.filter(user=request.user, licensee_id=licensee_id).first()
            )
            if not target_unit:
                raise UserManufacturingUnit.DoesNotExist
            
            # Update Active Profile
            SupplyChainUserProfile.objects.update_or_create(
                user=request.user,
                defaults={
                    'manufacturing_unit_name': target_unit.manufacturing_unit_name,
                    'licensee_id': approved_license_id or target_unit.licensee_id,
                    'license_type': target_unit.license_type,
                    'address': target_unit.address
                }
            )
            return Response({'success': True, 'message': f'Switched to {target_unit.manufacturing_unit_name}'})
            
        except UserManufacturingUnit.DoesNotExist:
             return Response({'success': False, 'error': 'Unit not found in your history'}, status=404)
