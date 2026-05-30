from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import LicenseApplication
from .serializers import LicenseApplicationSerializer


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_license_application(request):
    """
    Create a minimal license renewal record (stored in `license_application` table).
    """
    serializer = LicenseApplicationSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    obj = serializer.save()
    return Response(LicenseApplicationSerializer(obj).data, status=status.HTTP_201_CREATED)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def list_license_applications(request):
    qs = LicenseApplication.objects.all()
    if not getattr(request.user, "is_staff", False) and not getattr(request.user, "is_superuser", False):
        qs = qs.filter(applicant=request.user)
    data = LicenseApplicationSerializer(qs.order_by("-application_id"), many=True).data
    return Response(data, status=status.HTTP_200_OK)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def license_application_detail(request, pk):
    obj = get_object_or_404(LicenseApplication, application_id=str(pk))
    return Response(LicenseApplicationSerializer(obj).data, status=status.HTTP_200_OK)
