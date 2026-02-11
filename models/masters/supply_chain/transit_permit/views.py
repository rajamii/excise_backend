from rest_framework import viewsets
from .models import TransitPermitBottleType, BrandMlInCases
from .serializers import TransitPermitBottleTypeSerializer, BrandMlInCasesSerializer

class TransitPermitBottleTypeViewSet(viewsets.ModelViewSet):
    queryset = TransitPermitBottleType.objects.filter(is_active=True)
    serializer_class = TransitPermitBottleTypeSerializer

class BrandMlInCasesViewSet(viewsets.ModelViewSet):
    queryset = BrandMlInCases.objects.all().order_by('ml')
    serializer_class = BrandMlInCasesSerializer
