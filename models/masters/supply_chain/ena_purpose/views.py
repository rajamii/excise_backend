from rest_framework import viewsets, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from auth.roles.permissions import HasAppPermission  # type: ignore
from .models import Purpose
from .serializers import PurposeSerializer


class PurposeViewSet(viewsets.ModelViewSet):
    queryset = Purpose.objects.all()
    serializer_class = PurposeSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ['get']  # Only allow GET requests

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        serializer = self.get_serializer(queryset, many=True)
        return Response({
            'status': 'success',
            'data': serializer.data,
            'message': 'Purposes retrieved successfully'
        })


# ── Site Admin CRUD ──────────────────────────────────────────────────────────

@permission_classes([HasAppPermission('masters', 'view')])
@api_view(['GET'])
def purpose_admin_list(request):
    serializer = PurposeSerializer(
        Purpose.objects.all().order_by('purpose_id'), many=True
    )
    return Response(serializer.data, status=status.HTTP_200_OK)


@permission_classes([HasAppPermission('masters', 'create')])
@api_view(['POST'])
def purpose_create(request):
    serializer = PurposeSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(serializer.data, status=status.HTTP_201_CREATED)


@permission_classes([HasAppPermission('masters', 'view')])
@api_view(['GET'])
def purpose_detail(request, pk: int):
    try:
        obj = Purpose.objects.get(pk=pk)
    except Purpose.DoesNotExist:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
    serializer = PurposeSerializer(obj)
    return Response(serializer.data, status=status.HTTP_200_OK)


@permission_classes([HasAppPermission('masters', 'update')])
@api_view(['PUT', 'PATCH'])
def purpose_update(request, pk: int):
    try:
        obj = Purpose.objects.get(pk=pk)
    except Purpose.DoesNotExist:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
    serializer = PurposeSerializer(
        instance=obj, data=request.data, partial=request.method == 'PATCH'
    )
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(serializer.data, status=status.HTTP_200_OK)


@permission_classes([HasAppPermission('masters', 'delete')])
@api_view(['DELETE'])
def purpose_delete(request, pk: int):
    try:
        obj = Purpose.objects.get(pk=pk)
    except Purpose.DoesNotExist:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
    obj.delete()
    return Response({'message': 'Deleted successfully.'}, status=status.HTTP_200_OK)


@permission_classes([HasAppPermission('masters', 'update')])
@api_view(['PATCH'])
def purpose_toggle_active(request, pk: int):
    """Toggle the is_active status of a purpose."""
    try:
        obj = Purpose.objects.get(pk=pk)
    except Purpose.DoesNotExist:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
    obj.is_active = not obj.is_active
    obj.save(update_fields=['is_active', 'updated_at'])
    serializer = PurposeSerializer(obj)
    return Response(serializer.data, status=status.HTTP_200_OK)
