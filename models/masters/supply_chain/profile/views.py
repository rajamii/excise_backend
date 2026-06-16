from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from django.utils import timezone
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


class UserProfileAPIView(APIView):
    """
    Returns the active license profile for the currently logged-in licensee user.
    This resolves the user's *own* issued license_id directly from their licenses
    queryset, without crossing over to other users' application aliases.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        now_dt = timezone.now()

        # 1) Try to get from UserManufacturingUnit first (most explicit)
        units = UserManufacturingUnit.objects.filter(user=user).order_by('-updated_at', '-id')
        if units.exists():
            unit = units.first()
            return Response({
                'success': True,
                'exists': True,
                'data': {
                    'licensee_id': unit.licensee_id,
                    'manufacturing_unit_name': unit.manufacturing_unit_name,
                    'license_type': unit.license_type or '',
                }
            })

        # 2) Fall back to the user's own issued license
        licenses = getattr(user, 'licenses', None)
        if licenses is not None:
            # Try active & valid license first
            lic = (
                licenses
                .filter(is_active=True, valid_up_to__gte=now_dt)
                .exclude(license_id__isnull=True)
                .exclude(license_id='')
                .order_by('-issue_date')
                .select_related('license_sub_category')
                .first()
            )
            if not lic:
                # Fall back to any active license
                lic = (
                    licenses
                    .filter(is_active=True)
                    .exclude(license_id__isnull=True)
                    .exclude(license_id='')
                    .order_by('-issue_date')
                    .select_related('license_sub_category')
                    .first()
                )

            if lic:
                sub_cat_name = ''
                if lic.license_sub_category:
                    sub_cat_name = str(lic.license_sub_category.description or '').strip()

                # Derive manufacturing unit name from linked application if possible
                unit_name = ''
                try:
                    from models.transactional.new_license_application.models import NewLicenseApplication
                    app = NewLicenseApplication.objects.filter(
                        application_id=lic.source_object_id
                    ).only('establishment_name').first()
                    if app:
                        unit_name = str(app.establishment_name or '').strip()
                except Exception:
                    pass

                return Response({
                    'success': True,
                    'exists': True,
                    'data': {
                        'licensee_id': lic.license_id,
                        'manufacturing_unit_name': unit_name,
                        'license_type': sub_cat_name,
                    }
                })

        return Response({
            'success': True,
            'exists': False,
            'data': None
        })

    def post(self, request):
        """Create or update the user's manufacturing unit profile."""
        user = request.user
        data = request.data
        licensee_id = str(data.get('licensee_id') or data.get('licenseId') or '').strip()
        unit_name = str(data.get('manufacturing_unit_name') or data.get('manufacturingUnitName') or '').strip()
        license_type = str(data.get('license_type') or data.get('licenseType') or '').strip()

        if not licensee_id or not unit_name:
            return Response(
                {'success': False, 'error': 'licensee_id and manufacturing_unit_name are required.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        unit, created = UserManufacturingUnit.objects.update_or_create(
            user=user,
            licensee_id=licensee_id,
            defaults={
                'manufacturing_unit_name': unit_name,
                'license_type': license_type,
            }
        )
        return Response({
            'success': True,
            'created': created,
            'data': {
                'licensee_id': unit.licensee_id,
                'manufacturing_unit_name': unit.manufacturing_unit_name,
                'license_type': unit.license_type or '',
            }
        }, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

    def delete(self, request):
        """Clear the user's manufacturing unit profile."""
        deleted_count, _ = UserManufacturingUnit.objects.filter(user=request.user).delete()
        return Response({'success': True, 'deleted': deleted_count})
