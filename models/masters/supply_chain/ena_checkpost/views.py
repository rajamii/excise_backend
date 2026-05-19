from rest_framework import viewsets, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from auth.roles.permissions import HasAppPermission  # type: ignore
from .models import Checkpost
from .serializers import CheckpostSerializer


class CheckpostViewSet(viewsets.ModelViewSet):
    queryset = Checkpost.objects.all()
    serializer_class = CheckpostSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ['get']  # Only allow GET requests

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        serializer = self.get_serializer(queryset, many=True)
        return Response({
            'status': 'success',
            'data': serializer.data,
            'message': 'Checkposts retrieved successfully'
        })


# ── Site Admin CRUD ──────────────────────────────────────────────────────────

@permission_classes([HasAppPermission('masters', 'view')])
@api_view(['GET'])
def checkpost_admin_list(request):
    serializer = CheckpostSerializer(
        Checkpost.objects.all().order_by('check_post_id'), many=True
    )
    return Response(serializer.data, status=status.HTTP_200_OK)


@permission_classes([HasAppPermission('masters', 'create')])
@api_view(['POST'])
def checkpost_create(request):
    serializer = CheckpostSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(serializer.data, status=status.HTTP_201_CREATED)


@permission_classes([HasAppPermission('masters', 'view')])
@api_view(['GET'])
def checkpost_detail(request, pk: int):
    try:
        obj = Checkpost.objects.get(pk=pk)
    except Checkpost.DoesNotExist:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
    serializer = CheckpostSerializer(obj)
    return Response(serializer.data, status=status.HTTP_200_OK)


@permission_classes([HasAppPermission('masters', 'update')])
@api_view(['PUT', 'PATCH'])
def checkpost_update(request, pk: int):
    try:
        obj = Checkpost.objects.get(pk=pk)
    except Checkpost.DoesNotExist:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
    serializer = CheckpostSerializer(
        instance=obj, data=request.data, partial=request.method == 'PATCH'
    )
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(serializer.data, status=status.HTTP_200_OK)


@permission_classes([HasAppPermission('masters', 'delete')])
@api_view(['DELETE'])
def checkpost_delete(request, pk: int):
    try:
        obj = Checkpost.objects.get(pk=pk)
    except Checkpost.DoesNotExist:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
    obj.delete()
    return Response({'message': 'Deleted successfully.'}, status=status.HTTP_200_OK)


@permission_classes([HasAppPermission('masters', 'update')])
@api_view(['PATCH'])
def checkpost_toggle_active(request, pk: int):
    """Toggle the is_active status of a checkpost."""
    try:
        obj = Checkpost.objects.get(pk=pk)
    except Checkpost.DoesNotExist:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
    obj.is_active = not obj.is_active
    obj.save(update_fields=['is_active', 'updated_at'])
    serializer = CheckpostSerializer(obj)
    return Response(serializer.data, status=status.HTTP_200_OK)
