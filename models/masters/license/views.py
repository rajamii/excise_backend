from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.parsers import JSONParser
from rest_framework.response import Response
from rest_framework import status
from auth.roles.permissions import HasAppPermission
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
@api_view(['GET'])
@parser_classes([JSONParser])
def print_license_view(request, license_id):
    license = get_object_or_404(License, license_id=license_id)

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
    
    licenses = License.objects.filter(is_active=True).select_related(
        'excise_district', 'license_category'
    )

    district_code = request.query_params.get('district_code')
    if district_code:
        licenses = licenses.filter(excise_district__district_code=district_code)

    serializer = LicenseDetailSerializer(licenses, many=True)

    data = []
    for item in serializer.data:
        app_data = item.get('application_data', {})
        data.append({
            "id": item['license_id'],
            "license_id": item['license_id'],
            "establishment_name": app_data.get('establishment_name', ''),
            "license_category": item['license_category_name'],
            "district": item['excise_district_name'],
            "status": "Active"
        })

    return Response(data)