from rest_framework import viewsets
from .models import TransitPermitBottleType
from .serializers import TransitPermitBottleTypeSerializer

class TransitPermitBottleTypeViewSet(viewsets.ModelViewSet):
    queryset = TransitPermitBottleType.objects.filter(is_active=True)
    serializer_class = TransitPermitBottleTypeSerializer
