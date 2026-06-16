from rest_framework import permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from django.shortcuts import get_object_or_404

from .models import MasterHologramSupplier
from .serializers import MasterHologramSupplierSerializer


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def hologram_supplier_list(request):
    """List all hologram suppliers."""
    active_only = str(request.query_params.get('active_only') or '0').strip().lower()
    qs = MasterHologramSupplier.objects.all().order_by('company_name')
    if active_only in {'1', 'true', 'yes', 'y'}:
        qs = qs.filter(is_active=True)
    serializer = MasterHologramSupplierSerializer(qs, many=True)
    return Response(serializer.data)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def hologram_supplier_create(request):
    """Create a new hologram supplier."""
    serializer = MasterHologramSupplierSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(serializer.data, status=status.HTTP_201_CREATED)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def hologram_supplier_detail(request, pk):
    """Retrieve a hologram supplier instance."""
    supplier = get_object_or_404(MasterHologramSupplier, pk=pk)
    serializer = MasterHologramSupplierSerializer(supplier)
    return Response(serializer.data)


@api_view(['PUT', 'PATCH'])
@permission_classes([permissions.IsAuthenticated])
def hologram_supplier_update(request, pk):
    """Update a hologram supplier instance."""
    supplier = get_object_or_404(MasterHologramSupplier, pk=pk)
    serializer = MasterHologramSupplierSerializer(
        supplier, data=request.data, partial=request.method == 'PATCH'
    )
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(serializer.data)


@api_view(['DELETE'])
@permission_classes([permissions.IsAuthenticated])
def hologram_supplier_delete(request, pk):
    """Delete a hologram supplier instance."""
    supplier = get_object_or_404(MasterHologramSupplier, pk=pk)
    supplier.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)

