from rest_framework import permissions
from rest_framework import viewsets
from .models import NodalOfficer, PublicInformationOfficer, DirectorateAndDistrictOfficials, GrievanceRedressalOfficer
from .serializers import NodalOfficerSerializer, PublicInformationOfficerSerializer, DirectorateAndDistrictOfficialsSerializer, GrievanceRedressalOfficerSerializer

class NodalOfficerViewSet(viewsets.ModelViewSet):
    queryset = NodalOfficer.objects.all()
    serializer_class = NodalOfficerSerializer

    # Set permission so only admin can update, write, and delete
    permission_classes = [permissions.IsAdminUser]

class PublicInformationOfficerViewSet(viewsets.ModelViewSet):
    queryset = PublicInformationOfficer.objects.all()
    serializer_class = PublicInformationOfficerSerializer

    # Admins can update, write, delete, others can view
    permission_classes = [permissions.IsAdminUser]

class DirectorateAndDistrictOfficialsViewSet(viewsets.ModelViewSet):
    queryset = DirectorateAndDistrictOfficials.objects.all()
    serializer_class = DirectorateAndDistrictOfficialsSerializer

    # Admins can update, write, delete, others can view
    permission_classes = [permissions.IsAdminUser]

class GrievanceRedressalOfficerViewSet(viewsets.ModelViewSet):
    queryset = GrievanceRedressalOfficer.objects.all()
    serializer_class = GrievanceRedressalOfficerSerializer

    # Admins can update, write, delete, others can view
    permission_classes = [permissions.IsAdminUser]
