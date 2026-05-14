from rest_framework import generics, permissions
from rest_framework.response import Response

from .models import MasterHologramSupplier
from .serializers import MasterHologramSupplierSerializer


class MasterHologramSupplierListAPIView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = MasterHologramSupplierSerializer
    queryset = MasterHologramSupplier.objects.all().order_by('company_name')

    def get_queryset(self):
        qs = super().get_queryset()
        active_only = str(self.request.query_params.get('active_only') or '1').strip().lower()
        if active_only in {'1', 'true', 'yes', 'y'}:
            qs = qs.filter(is_active=True)
        return qs

    def list(self, request, *args, **kwargs):
        serializer = self.get_serializer(self.get_queryset(), many=True)
        return Response({'success': True, 'data': serializer.data})

