from rest_framework import viewsets
from rest_framework.permissions import AllowAny
from .models import EnaRevalidationDetail
from .serializers import EnaRevalidationDetailSerializer

class EnaRevalidationDetailViewSet(viewsets.ModelViewSet):
    queryset = EnaRevalidationDetail.objects.all().order_by('-created_at')
    serializer_class = EnaRevalidationDetailSerializer
    permission_classes = [AllowAny]
