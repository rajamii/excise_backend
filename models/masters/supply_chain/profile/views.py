from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from django.db import connection
from .models import SupplyChainUserProfile
from .serializers import SupplyChainUserProfileSerializer

class ManufacturingUnitListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        try:
            with connection.cursor() as cursor:
                # User requested to use ONLY liquor_data_details
                # Fetch names
                cursor.execute("""
                    SELECT DISTINCT manufacturing_unit_name, MAX(liquor_type)
                    FROM liquor_data_details
                    WHERE manufacturing_unit_name IS NOT NULL
                    GROUP BY manufacturing_unit_name
                """)
                rows = cursor.fetchall()

            data = []
            for row in rows:
                name = row[0]
                l_type_raw = row[1] if row[1] else ''
                
                # Determine type
                l_type = 'Brewery' if 'beer' in l_type_raw.lower() else 'Distillery'
                
                # Dynamic ID Generation
                # Dynamic ID Generation
                # Generate a deterministic ID based on the name hash
                # Format: 99 + Year(25) + 5 digits from hash
                # We use a fixed seed/salt logic implicitly by the name string
                import hashlib
                hash_object = hashlib.md5(name.encode())
                hash_int = int(hash_object.hexdigest(), 16)
                unique_part = str(hash_int % 100000).zfill(5)
                licensee_id = f"992025{unique_part}"

                data.append({
                    'name': name,
                    'licensee_id': licensee_id, 
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
            
            UserManufacturingUnit.objects.update_or_create(
                user=request.user, 
                licensee_id=unit_data['licensee_id'],
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
                    'licensee_id': unit_data['licensee_id'],
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
            # Find the unit in history
            target_unit = UserManufacturingUnit.objects.get(user=request.user, licensee_id=licensee_id)
            
            # Update Active Profile
            SupplyChainUserProfile.objects.update_or_create(
                user=request.user,
                defaults={
                    'manufacturing_unit_name': target_unit.manufacturing_unit_name,
                    'licensee_id': target_unit.licensee_id,
                    'license_type': target_unit.license_type,
                    'address': target_unit.address
                }
            )
            return Response({'success': True, 'message': f'Switched to {target_unit.manufacturing_unit_name}'})
            
        except UserManufacturingUnit.DoesNotExist:
             return Response({'success': False, 'error': 'Unit not found in your history'}, status=404)
