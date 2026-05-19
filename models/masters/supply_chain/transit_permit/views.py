from rest_framework import viewsets
from rest_framework.permissions import AllowAny, IsAuthenticated
from auth.roles.permissions import HasAppPermission
from .models import BrandMlInCases
from models.masters.supply_chain.liquor_data.models import MasterBottleType
from .serializers import TransitPermitBottleTypeSerializer, BrandMlInCasesSerializer

class TransitPermitBottleTypeViewSet(viewsets.ModelViewSet):
    queryset = MasterBottleType.objects.filter(is_active=True)
    serializer_class = TransitPermitBottleTypeSerializer

    def get_permissions(self):
        # Used by licensees; reads can be public/authenticated. Mutations are Site Admin only.
        if self.action in {'list', 'retrieve'}:
            return [AllowAny()]
        if self.action == 'create':
            return [HasAppPermission('masters', 'create')]
        if self.action in {'update', 'partial_update'}:
            return [HasAppPermission('masters', 'update')]
        if self.action == 'destroy':
            return [HasAppPermission('masters', 'delete')]
        return [IsAuthenticated()]

class BrandMlInCasesViewSet(viewsets.ModelViewSet):
    queryset = BrandMlInCases.objects.all().order_by('ml')
    serializer_class = BrandMlInCasesSerializer

    def get_permissions(self):
        # Used by licensees; reads can be public/authenticated. Mutations are Site Admin only.
        if self.action in {'list', 'retrieve'}:
            return [AllowAny()]
        if self.action == 'create':
            return [HasAppPermission('masters', 'create')]
        if self.action in {'update', 'partial_update'}:
            return [HasAppPermission('masters', 'update')]
        if self.action == 'destroy':
            return [HasAppPermission('masters', 'delete')]
        return [IsAuthenticated()]
