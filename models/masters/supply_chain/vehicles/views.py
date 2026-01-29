from rest_framework import viewsets, permissions
from rest_framework.response import Response
from .models import Vehicle
from .serializers import VehicleSerializer

class VehicleViewSet(viewsets.ModelViewSet):
    queryset = Vehicle.objects.all().order_by('vehicle_number')
    serializer_class = VehicleSerializer
    permission_classes = [permissions.AllowAny] # Or IsAuthenticated depending on requirements

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        serializer = self.get_serializer(queryset, many=True)
        return Response({
            'success': True,
            'data': serializer.data
        })
