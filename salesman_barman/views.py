from rest_framework import generics
from .models import SalesmanBarmanDetails, DocumentsDetails
from .serializers import SalesmanBarmanDetailsSerializer, DocumentsDetailsSerializer


class SalesmanBarmanList(generics.ListCreateAPIView):
    queryset = SalesmanBarmanDetails.objects.all()
    serializer_class = SalesmanBarmanDetailsSerializer


class SalesmanBarmanDetails(generics.RetrieveUpdateDestroyAPIView):
    queryset = SalesmanBarmanDetails.objects.all()
    serializer_class = SalesmanBarmanDetailsSerializer


class DocumentsDetailsList(generics.ListCreateAPIView):
    queryset = DocumentsDetails.objects.all()
    serializer_class = DocumentsDetailsSerializer


class DocumentsDetailsDetails(generics.RetrieveUpdateDestroyAPIView):
    queryset = DocumentsDetails.objects.all()
    serializer_class = DocumentsDetailsSerializer

