from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework import status
from auth.roles.permissions import HasAppPermission
from .models import License
from .serializers import LicenseSerializer

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
def license_detail(request, license_id):
    """
    Retrieve details of a specific license by its license_id.
    """
    license = get_object_or_404(License, license_id=license_id)
    serializer = LicenseSerializer(license)
    return Response(serializer.data, status=status.HTTP_200_OK)