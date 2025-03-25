from django.urls import path
from rest_framework import generics
from .models import CompanyDetails, MemberDetails, DocumentDetails  # Replace with your actual models
from .serializers import CompanyDetailsSerializer, MemberDetailsSerializer, DocumentDetailsSerializer # Replace with your actual serializers

class CompanyDetailsList(generics.ListCreateAPIView):
    queryset = CompanyDetails.objects.all()
    serializer_class = CompanyDetailsSerializer

class CompanyDetailsDetail(generics.RetrieveUpdateDestroyAPIView):
    queryset = CompanyDetails.objects.all()
    serializer_class = CompanyDetailsSerializer


class MemberDetailsList(generics.ListCreateAPIView):
    queryset = MemberDetails.objects.all()
    serializer_class = MemberDetailsSerializer

class MemberDetailsDetail(generics.RetrieveUpdateDestroyAPIView):
    queryset = MemberDetails.objects.all()
    serializer_class = MemberDetailsSerializer

 
class DocumentDetailsList(generics.ListCreateAPIView):
    queryset = DocumentDetails.objects.all()
    serializer_class = DocumentDetailsSerializer

class DocumentDetailsDetail(generics.RetrieveUpdateDestroyAPIView):
    queryset = DocumentDetails.objects.all()
    serializer_class = DocumentDetailsSerializer
