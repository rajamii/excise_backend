from rest_framework import viewsets
from .models import StatusMaster
from .serializers import StatusMasterSerializer

class StatusMasterViewSet(viewsets.ModelViewSet):
    queryset = StatusMaster.objects.filter(is_active=True)
    serializer_class = StatusMasterSerializer
