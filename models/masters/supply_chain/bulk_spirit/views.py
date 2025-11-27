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
    
    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        return Response({
            'success': True,
            'data': serializer.data
        })
