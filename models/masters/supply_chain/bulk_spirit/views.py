from rest_framework import generics, permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from auth.roles.permissions import HasAppPermission  # type: ignore
from .models import BulkSpiritType
from .serializers import BulkSpiritTypeSerializer
from models.masters.supply_chain.scoping import is_licensee_or_oic_user, user_scoped_license_ids

class BulkSpiritTypeListAPIView(generics.ListAPIView):
    """
    API view to list all bulk spirit types.
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BulkSpiritTypeSerializer
    queryset = BulkSpiritType.objects.all().order_by('sprit_id')

    def get_queryset(self):
        queryset = super().get_queryset()
        sub_category_id = self.request.query_params.get('license_sub_category_id')
        if sub_category_id:
            try:
                if int(sub_category_id) != 2:
                    return queryset.none()
            except (TypeError, ValueError):
                return queryset.none()

        # Licensee/OIC users see only bulk spirits assigned to their license ids.
        if is_licensee_or_oic_user(self.request.user):
            scoped = user_scoped_license_ids(self.request.user)
            if not scoped:
                return queryset.none()
            queryset = queryset.filter(license_id__in=list(scoped))

        return queryset
    
    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        return Response({
            'success': True,
            'data': serializer.data
        })


@permission_classes([HasAppPermission("masters", "view")])
@api_view(["GET"])
def bulk_spirit_type_admin_list(request):
    serializer = BulkSpiritTypeSerializer(BulkSpiritType.objects.all().order_by("sprit_id"), many=True)
    return Response(serializer.data, status=status.HTTP_200_OK)


@permission_classes([HasAppPermission("masters", "create")])
@api_view(["POST"])
def bulk_spirit_type_create(request):
    serializer = BulkSpiritTypeSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(serializer.data, status=status.HTTP_201_CREATED)


@permission_classes([HasAppPermission("masters", "view")])
@api_view(["GET"])
def bulk_spirit_type_detail(request, pk: int):
    try:
        obj = BulkSpiritType.objects.get(pk=pk)
    except BulkSpiritType.DoesNotExist:
        return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
    serializer = BulkSpiritTypeSerializer(obj)
    return Response(serializer.data, status=status.HTTP_200_OK)


@permission_classes([HasAppPermission("masters", "update")])
@api_view(["PUT", "PATCH"])
def bulk_spirit_type_update(request, pk: int):
    try:
        obj = BulkSpiritType.objects.get(pk=pk)
    except BulkSpiritType.DoesNotExist:
        return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

    serializer = BulkSpiritTypeSerializer(instance=obj, data=request.data, partial=request.method == "PATCH")
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(serializer.data, status=status.HTTP_200_OK)


@permission_classes([HasAppPermission("masters", "delete")])
@api_view(["DELETE"])
def bulk_spirit_type_delete(request, pk: int):
    try:
        obj = BulkSpiritType.objects.get(pk=pk)
    except BulkSpiritType.DoesNotExist:
        return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
    obj.delete()
    return Response({"message": "Deleted successfully."}, status=status.HTTP_200_OK)
