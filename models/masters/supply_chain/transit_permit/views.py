from rest_framework import viewsets
from .models import BrandMlInCases
from models.masters.supply_chain.liquor_data.models import MasterBottleType
from .serializers import TransitPermitBottleTypeSerializer, BrandMlInCasesSerializer

class TransitPermitBottleTypeViewSet(viewsets.ModelViewSet):
    queryset = MasterBottleType.objects.filter(is_active=True)
    serializer_class = TransitPermitBottleTypeSerializer

class BrandMlInCasesViewSet(viewsets.ModelViewSet):
    queryset = BrandMlInCases.objects.all().order_by('ml')
    serializer_class = BrandMlInCasesSerializer
