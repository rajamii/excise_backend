from django.shortcuts import get_object_or_404
from django.utils.timezone import now
from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.parsers import JSONParser
from rest_framework.response import Response
from rest_framework import status
from auth.roles.permissions import HasAppPermission  # type: ignore
from .models import License
from .serializers import LicenseSerializer, LicenseDetailSerializer

@permission_classes([HasAppPermission('license', 'view')])
@api_view(['GET'])
def list_licenses(request):
    """
    List all licenses.
    """
    licenses = License.objects.all()
    serializer = LicenseSerializer(licenses, many=True)
    return Response(serializer.data, status=status.HTTP_200_OK)

@permission_classes([HasAppPermission('license', 'view')])
@api_view(['POST'])
@parser_classes([JSONParser])
def print_license_view(request, application_id):
    license = get_object_or_404(License, application_id=application_id)

    if not license.is_approved:
        return Response({"error": "License is not approved yet."}, status=403)

    can_print, fee = license.can_print_license()

    if not can_print:
        return Response({
            "error": "Print limit exceeded. Please pay ₹500 to continue printing.",
            "fee_required": fee
        }, status=403)

    if fee > 0 and not license.is_print_fee_paid:
        return Response({"error": "₹500 fee not paid yet."}, status=403)

    license.record_license_print(fee_paid=(fee > 0))

    return Response({
        "success": "License printed.",
        "print_count": license.print_count
    })


@permission_classes([HasAppPermission('license', 'view')])
@api_view(['GET'])
def license_detail(request, license_id):
    license = get_object_or_404(License, license_id=license_id)
    serializer = LicenseDetailSerializer(license)
    return Response(serializer.data, status=status.HTTP_200_OK)


@permission_classes([HasAppPermission('license', 'view')])
@api_view(['GET'])
def active_licensees(request):
    """
    Return active licenses from the License master table that can be used 
    for Salesman/Barman registration.
    
    This queries the License MASTER table (not LicenseApplication) to find 
    active licenses that are valid and can have salesman/barman attached.
    
    Query params:
    - district_code: Filter by district code (e.g., "101")
    - license_category: Filter by license category ID (e.g., "1")
    - mode: Filter by mode of operation (e.g., "salesman" or "barman") - optional
    """
    district_code = request.query_params.get('district_code')
    license_category = request.query_params.get('license_category')
    mode = request.query_params.get('mode')
    
    # Query the License MASTER table for active licenses
    licenses = License.objects.filter(
        is_active=True,
        valid_up_to__gte=now().date()  # Only include licenses that haven't expired
    ).select_related(
        'excise_district',
        'license_category',
        'source_content_type'
    )
    
    # Apply filters
    if district_code:
        licenses = licenses.filter(excise_district__district_code=district_code)
    
    if license_category:
        licenses = licenses.filter(license_category_id=license_category)
    
    # Build response data
    data = []
    for lic in licenses:
        # Get the source application to extract establishment name and mode
        source_app = lic.source_application
        establishment_name = "N/A"
        mode_of_operation = "N/A"
        
        if source_app:
            # Extract establishment name from source application
            if hasattr(source_app, 'establishment_name'):
                establishment_name = source_app.establishment_name
            
            # Extract mode of operation if it exists
            if hasattr(source_app, 'mode_of_operation'):
                mode_of_operation = source_app.mode_of_operation
                
                # Filter by mode if provided
                if mode:
                    mode_formatted = mode.capitalize()
                    if mode_of_operation != mode_formatted:
                        continue  # Skip this license if mode doesn't match
        
        # If we're filtering by mode but source has no mode_of_operation, skip it
        if mode and mode_of_operation == "N/A":
            continue
        
        data.append({
            "licenseeId": lic.license_id,  # String primary key (e.g., "LA/101/2025-26/0001")
            "id": lic.license_id,  # Also include as 'id' for consistency
            "establishmentName": establishment_name,
            "license_category": lic.license_category.license_category if lic.license_category else "N/A",
            "district": lic.excise_district.district if lic.excise_district else "N/A",
            "district_code": lic.excise_district.district_code if lic.excise_district else "N/A",
            "mode_of_operation": mode_of_operation,
            "status": "Active",
            "valid_up_to": lic.valid_up_to.strftime('%Y-%m-%d')
        })
    
    return Response(data, status=status.HTTP_200_OK)