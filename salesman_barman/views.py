from rest_framework import viewsets
from .models import SalesmanBarmanDetails, DocumentsDetails
from .serializers import SalesmanBarmanDetailsSerializer, DocumentsDetailsSerializer

class SalesmanBarmanDetailsViewSet(viewsets.ModelViewSet):
    queryset = SalesmanBarmanDetails.objects.all()
    serializer_class = SalesmanBarmanDetailsSerializer

class DocumentsDetailsViewSet(viewsets.ModelViewSet):
    queryset = DocumentsDetails.objects.all()
    serializer_class = DocumentsDetailsSerializer
