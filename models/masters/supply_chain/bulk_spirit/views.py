from rest_framework import generics, permissions
from rest_framework.response import Response
from .models import BulkSpiritType
from .serializers import BulkSpiritTypeSerializer

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

        # Requisition import permit is only for distillery users.
        # If a brewery user deep-links to the page, return empty options.
        if sub_category_id:
            try:
                if int(sub_category_id) != 2:
                    return queryset.none()
            except (TypeError, ValueError):
                return queryset.none()

        return queryset
    
    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        return Response({
            'success': True,
            'data': serializer.data
        })
