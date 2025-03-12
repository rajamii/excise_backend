from rest_framework import viewsets
from .models import CompanyDetails, MemberDetails, DocumentDetails
from .serializers import CompanyDetailsSerializer, MemberDetailsSerializer, DocumentDetailsSerializer

class CompanyDetailsViewSet(viewsets.ModelViewSet):
    queryset = CompanyDetails.objects.all()
    serializer_class = CompanyDetailsSerializer

class MemberDetailsViewSet(viewsets.ModelViewSet):
    queryset = MemberDetails.objects.all()
    serializer_class = MemberDetailsSerializer

class DocumentDetailsViewSet(viewsets.ModelViewSet):
    queryset = DocumentDetails.objects.all()
    serializer_class = DocumentDetailsSerializer
