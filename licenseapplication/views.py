from rest_framework import viewsets
from .models import LicenseApplication
from .serializers import LicenseApplicationSerializer

class LicenseApplicationViewSet(viewsets.ModelViewSet):
    queryset = LicenseApplication.objects.all()
    serializer_class = LicenseApplicationSerializer
