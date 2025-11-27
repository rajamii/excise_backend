from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
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
