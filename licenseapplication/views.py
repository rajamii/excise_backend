from rest_framework import generics
from .models import LicenseApplication
from .serializers import LicenseApplicationSerializer

class LicenseApplicationCreateView(generics.CreateAPIView):
    queryset = LicenseApplication.objects.all()
    serializer_class = LicenseApplicationSerializer

class LicenseApplicationListView(generics.ListAPIView):
    queryset = LicenseApplication.objects.all()
    serializer_class = LicenseApplicationSerializer

class LicenseApplicationDetailView(generics.RetrieveAPIView):
    queryset = LicenseApplication.objects.all()
    serializer_class = LicenseApplicationSerializer
